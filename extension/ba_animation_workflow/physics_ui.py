"""Cancelable process orchestration and a self-contained Chinese physics panel."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

import bpy
from bpy.props import BoolProperty, IntProperty, PointerProperty, StringProperty
from . import physics

_jobs = set()


class BakeJob:
    def __init__(self, scene, rig, start, end, align=True, substeps=0, iterations=0, directory=None):
        self.scene, self.rig = scene, rig
        self.report = physics.preflight(scene, rig, start, end)
        self.guard = physics.fingerprint(scene, rig)
        self.folder = Path(tempfile.mkdtemp(prefix='baw_physics_', dir=directory))
        self.process = None
        self.log = None
        self.paths = {n: self.folder / n for n in ('snapshot.blend', 'job.json', 'progress.json', 'result.json', 'worker.log', 'progress.tmp', 'result.tmp')}
        try:
            # Writes only the snapshot; does not change bpy.data.filepath or
            # invoke save handlers on the artist's working file.
            bpy.data.libraries.write(str(self.paths['snapshot.blend']), {scene}, path_remap='ABSOLUTE', fake_user=True)
            payload = dict(self.report, scene=scene.name, snapshot=str(self.paths['snapshot.blend']),
                           result=str(self.paths['result.json']), progress=str(self.paths['progress.json']), align=align)
            if substeps:
                payload['substeps'] = substeps
            if iterations:
                payload['iterations'] = iterations
            self.paths['job.json'].write_text(json.dumps(payload, ensure_ascii=False), encoding='utf8')
            self.log = self.paths['worker.log'].open('w', encoding='utf8')
            command = [bpy.app.binary_path, '--background', '--disable-autoexec', '--python-exit-code', '1',
                       '--python', str(Path(__file__).with_name('physics_worker.py')), '--', str(self.paths['job.json'])]
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT,
                                            creationflags=flags, stdin=subprocess.DEVNULL)
            _jobs.add(self)
        except Exception:
            self.close()
            raise

    def progress(self):
        try:
            p = json.loads(self.paths['progress.json'].read_text(encoding='utf8'))
            return f"{p['stage']} · {p['done']}/{p['total']}"
        except (OSError, ValueError, KeyError):
            return '正在准备独立模拟副本…'

    def finish(self):
        if self.process.poll() is None:
            raise RuntimeError('物理任务仍在运行')
        self.close_log()
        try:
            result = json.loads(self.paths['result.json'].read_text(encoding='utf8'))
        except (OSError, ValueError) as exc:
            raise RuntimeError('独立模拟未完成；日志：' + str(self.paths['worker.log'])) from exc
        if self.process.returncode or result.get('status') != 'OK':
            raise RuntimeError(result.get('error', '独立模拟失败') + '；日志：' + str(self.paths['worker.log']))
        physics.apply_result(self.scene, self.rig, result, self.report, self.guard)
        text = bpy.data.texts.new('BAW_物理烘焙报告')
        text.write(json.dumps({k: v for k, v in result.items() if k != 'basis'}, ensure_ascii=False, indent=2))
        self.cleanup()
        _jobs.discard(self)
        return result

    def close_log(self):
        if self.log and not self.log.closed:
            self.log.close()

    def cleanup(self):
        # Only our own, named files; never recurse into user paths or symlinks.
        if not self.folder.name.startswith('baw_physics_') or self.folder.is_symlink():
            return
        for p in self.paths.values():
            if p.parent == self.folder:
                p.unlink(missing_ok=True)
        try:
            self.folder.rmdir()
        except OSError:
            pass

    def close(self, keep_logs=False):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.close_log()
        if not keep_logs:
            self.cleanup()
        else:
            # Retain diagnostics, not a large snapshot of the user's model.
            self.paths['snapshot.blend'].unlink(missing_ok=True)
        _jobs.discard(self)


class BAW_PG_physics(bpy.types.PropertyGroup):
    rig: PointerProperty(name='MMD 角色', type=bpy.types.Object, poll=lambda self, o: o.type == 'ARMATURE')
    start: IntProperty(name='预热起始', default=-30, min=-10000, max=100000)
    end: IntProperty(name='结束帧', default=250, min=-9999, max=100000)
    align: BoolProperty(name='校正已确认的统一偏移', default=True,
                        description='仅在模拟副本中校正多个关节高度一致的大幅偏移；无法可靠识别时停止并报告')
    substeps: IntProperty(name='每帧子步', default=0, min=0, max=1000, description='0 表示沿用工程设置')
    iterations: IntProperty(name='求解迭代', default=0, min=0, max=1000, description='0 表示沿用工程设置')
    status: StringProperty(options={'SKIP_SAVE'})


class BAW_OT_physics_range(bpy.types.Operator):
    bl_idname = 'baw.physics_use_range'
    bl_label = '读取动作与预热范围'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.baw_physics
        if not s.rig:
            obj = context.object
            if obj and obj.type == 'ARMATURE':
                s.rig = obj
            elif hasattr(context.scene, 'baw_finishing'):
                s.rig = context.scene.baw_finishing.rig
        if not s.rig:
            self.report({'ERROR'}, '请先选择角色骨架')
            return {'CANCELLED'}
        s.start, s.end = physics.infer_range(context.scene, s.rig)
        return {'FINISHED'}


class BAW_OT_physics_check(bpy.types.Operator):
    bl_idname = 'baw.physics_check'
    bl_label = '检查物理条件'

    def execute(self, context):
        s = context.scene.baw_physics
        try:
            report = physics.preflight(context.scene, s.rig, s.start, s.end)
            s.status = f"可进入隔离检查：{report['rigid_bodies']} 个刚体，{len(report['bones'])} 根物理骨骼；布局将在副本中复核"
        except (ValueError, RuntimeError) as exc:
            s.status = str(exc)
            self.report({'ERROR'}, s.status)
            return {'CANCELLED'}
        return {'FINISHED'}


class BAW_OT_physics_bake(bpy.types.Operator):
    bl_idname = 'baw.physics_bake'
    bl_label = '安全烘焙并应用'
    bl_description = '独立模拟并逐帧复核后应用；Esc 取消，原动作可恢复'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}
    _job = None
    _timer = None

    @classmethod
    def poll(cls, context):
        return not _jobs and context.mode == 'OBJECT'

    def execute(self, context):
        s = context.scene.baw_physics
        try:
            self._job = BakeJob(context.scene, s.rig, s.start, s.end, s.align, s.substeps, s.iterations)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        if bpy.app.background:
            self._job.process.wait()
            return self._finish(context)
        self._timer = context.window_manager.event_timer_add(.3, window=context.window)
        context.window_manager.modal_handler_add(self)
        s.status = '开始隔离模拟；Esc 可取消'
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self.cancel(context)
            context.scene.baw_physics.status = '已取消；原动作和物理状态未改变'
            return {'CANCELLED'}
        if event.type == 'TIMER':
            context.scene.baw_physics.status = self._job.progress()
            if context.area:
                context.area.tag_redraw()
            if self._job.process.poll() is not None:
                return self._finish(context)
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        self._remove_timer(context)
        try:
            result = self._job.finish()
            s = context.scene.baw_physics
            s.status = f"已验证并应用 {len(result['basis'])} 帧物理动作；原动作可恢复。请播放检查头发与衣物表现"
            self.report({'INFO'}, s.status)
            return {'FINISHED'}
        except Exception as exc:
            self._job.close(keep_logs=True)
            context.scene.baw_physics.status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def _remove_timer(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

    def cancel(self, context):
        self._remove_timer(context)
        if self._job:
            self._job.close()


class BAW_OT_physics_restore(bpy.types.Operator):
    bl_idname = 'baw.physics_restore'
    bl_label = '恢复烘焙前状态'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            physics.restore(context.scene, context.scene.baw_physics.rig)
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        context.scene.baw_physics.status = '已恢复原 Action 与物理开关；烘焙 Action 保留为备用'
        return {'FINISHED'}


class BAW_PT_physics(bpy.types.Panel):
    bl_idname = 'BAW_PT_physics'
    bl_label = 'MMD 物理与安全烘焙'
    bl_parent_id = 'BAW_PT_main'
    bl_category = 'BA 动画'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        from .panels import _wrapped
        l = self.layout
        s = context.scene.baw_physics
        col = l.column()
        col.enabled = not _jobs
        col.prop(s, 'rig')
        col.operator('baw.physics_use_range')
        row = col.row(align=True)
        row.prop(s, 'start')
        row.prop(s, 'end')
        _wrapped(col, context, '起始帧包含实际预热动作。保留原 FPS、正式出片范围和负帧。')
        col.prop(s, 'align')
        row = col.row(align=True)
        row.prop(s, 'substeps')
        row.prop(s, 'iterations')
        _wrapped(col, context, '求解参数为 0 时沿用工程设置。提高参数不能修复刚体错位。')
        col.operator('baw.physics_check', icon='CHECKMARK')
        col.operator('baw.physics_bake', icon='PHYSICS')
        _wrapped(col, context, '完成后使用独立物理 Action，暂停实时物理；可任意跳帧及保存重开。模拟期间 Esc 取消。')
        row = col.row()
        row.enabled = bool(s.rig and physics.BACKUP in s.rig)
        row.operator('baw.physics_restore', icon='LOOP_BACK')
        if s.status:
            _wrapped(l, context, s.status)


CLASSES = (BAW_PG_physics, BAW_OT_physics_range, BAW_OT_physics_check,
           BAW_OT_physics_bake, BAW_OT_physics_restore, BAW_PT_physics)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.baw_physics = PointerProperty(type=BAW_PG_physics)


def unregister():
    for job in tuple(_jobs):
        job.close()
    del bpy.types.Scene.baw_physics
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
