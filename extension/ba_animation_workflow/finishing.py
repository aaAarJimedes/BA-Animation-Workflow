"""Scene-space prop contacts and motion diagnostics, independent of generation."""
from __future__ import annotations
import json
import bpy
from bpy.props import PointerProperty, StringProperty, IntProperty, FloatProperty
from .utils import iter_action_fcurves


def _armature(_self,obj):
    return obj.type == 'ARMATURE'


def bake_prop_contact(scene, rig, prop, bone_name, start, end):
    """Bake an initially aligned prop to a moving hand, then leave it at release.

    The prop must be placed at the grasp location on `start` before invoking.
    No solver changes the character's hand; the existing hand animation drives it.
    Unparented, unconstrained props avoid ambiguous double transforms.
    """
    if rig is None or rig.type!='ARMATURE' or bone_name not in rig.pose.bones:
        raise ValueError('请选择角色和有效的持握骨骼')
    if prop is None or prop==rig or prop.name not in scene.objects or rig.name not in scene.objects:
        raise ValueError('道具和角色必须位于当前场景')
    if prop.library or prop.parent or prop.constraints:
        raise ValueError('道具需要可编辑、无父级且无约束；请使用独立道具副本')
    if end<=start or end-start>10000:
        raise ValueError('持握结束帧必须晚于开始帧，范围最多 10000 帧')
    ad=prop.animation_data
    if ad and (ad.action or ad.nla_tracks or ad.drivers):
        raise ValueError('道具已有动画；请先恢复本工具持握或使用无动画副本')
    frame,subframe=scene.frame_current,scene.frame_subframe
    original=prop.matrix_world.copy();mode=prop.rotation_mode
    action=None
    try:
        scene.frame_set(start);bpy.context.view_layer.update()
        deps=bpy.context.evaluated_depsgraph_get()
        er=rig.evaluated_get(deps)
        grip=er.matrix_world@er.pose.bones[bone_name].matrix
        offset=grip.inverted()@original
        samples=[]
        for f in range(start,end+1):
            scene.frame_set(f);bpy.context.view_layer.update()
            er=rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
            samples.append((f,er.matrix_world@er.pose.bones[bone_name].matrix@offset))
        action=bpy.data.actions.new('BAW_持握_'+prop.name)
        action['baw_contact_owner']=prop.name
        action['baw_contact_original_matrix']=json.dumps([list(row) for row in original])
        action['baw_contact_original_mode']=mode
        action['baw_contact_range']=[start,end]
        action['baw_contact_bone']=bone_name
        prop.animation_data_create().action=action;prop.rotation_mode='QUATERNION'
        previous=None
        for f,matrix in [(start-1,original)]+samples+[(end+1,samples[-1][1])]:
            loc,rot,scale=matrix.decompose()
            if previous is not None and previous.dot(rot)<0:rot.negate()
            prop.location=loc;prop.rotation_quaternion=rot;prop.scale=scale
            previous=rot.copy()
            for path in ('location','rotation_quaternion','scale'):prop.keyframe_insert(path,frame=f)
        for curve in iter_action_fcurves(action):
            curve.extrapolation='CONSTANT'
            for key in curve.keyframe_points:key.interpolation='LINEAR'
        return action
    except Exception:
        if action is not None:
            if prop.animation_data:prop.animation_data.action=None
            bpy.data.actions.remove(action)
        prop.rotation_mode=mode;prop.matrix_world=original
        raise
    finally:
        scene.frame_set(frame,subframe=subframe);bpy.context.view_layer.update()


def restore_prop_contact(prop):
    from mathutils import Matrix
    action=prop.animation_data.action if prop and prop.animation_data else None
    if not action or action.get('baw_contact_owner')!=prop.name:
        raise ValueError('当前道具没有本工具生成的持握动画')
    if action.users>1:
        raise ValueError('持握 Action 正被其他对象使用；请先解除共享')
    matrix=Matrix(json.loads(action['baw_contact_original_matrix']))
    mode=action['baw_contact_original_mode']
    prop.animation_data.action=None
    prop.rotation_mode=mode;prop.matrix_world=matrix
    bpy.data.actions.remove(action)


def inspect_motion(scene,rig,start,end,still_speed=.025,min_hold=12):
    if rig is None or rig.type!='ARMATURE':raise ValueError('请选择角色骨架')
    if end<=start or end-start>10000:raise ValueError('检查范围需要 2–10001 帧')
    names=[n for n in ('手首.R','手首.L','頭','RightHand','LeftHand','Head','c_hand_fk.l','c_hand_fk.r','c_head.x') if n in rig.pose.bones]
    if not names:raise ValueError('未识别手和头部骨骼；当前检查支持 MMD、SOMA 和 ARP 常用骨名')
    frame,sub=scene.frame_current,scene.frame_subframe
    fps=scene.render.fps/scene.render.fps_base
    runs=[];begin=None;previous=None;peaks=[]
    try:
        for f in range(start,end+1):
            scene.frame_set(f);bpy.context.view_layer.update()
            er=rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
            now={n:er.matrix_world@er.pose.bones[n].head for n in names}
            if previous:
                speed=max((now[n]-previous[n]).length for n in names)*fps*scene.unit_settings.scale_length
                if speed<still_speed:
                    if begin is None:begin=f-1
                elif begin is not None:
                    if f-begin>=min_hold:runs.append([begin,f-1])
                    begin=None
                peaks.append((speed,f))
            previous=now
        if begin is not None and end-begin+1>=min_hold:runs.append([begin,end])
    finally:
        scene.frame_set(frame,subframe=sub);bpy.context.view_layer.update()
    return {'fps':fps,'frames':[start,end],'sample_bones':names,'low_speed_intervals':runs,
            'largest_speeds_m_s':[{'frame':f,'speed':round(v,4)} for v,f in sorted(peaks,reverse=True)[:8]],
            'note':'低速区间是待检查候选，不代表必须删除；关键接触和有意停留应保留。FPS 和动作未修改。'}


class BAW_PG_finishing(bpy.types.PropertyGroup):
    rig:PointerProperty(name='角色',type=bpy.types.Object,poll=_armature)
    prop:PointerProperty(name='道具',type=bpy.types.Object)
    bone:StringProperty(name='持握骨骼',default='手首.R')
    start:IntProperty(name='开始帧',default=1,min=-10000,max=100000)
    end:IntProperty(name='放下帧',default=120,min=-10000,max=100000)
    still_speed:FloatProperty(name='低速阈值 m/s',default=.025,min=.001,max=.2,precision=3)
    min_hold:IntProperty(name='连续低速帧',default=12,min=3,max=240)
    status:StringProperty(options={'SKIP_SAVE'})


class BAW_OT_prop_contact(bpy.types.Operator):
    bl_idname='baw.prop_contact';bl_label='烘焙持握 → 放下';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        s=context.scene.baw_finishing
        try:
            action=bake_prop_contact(context.scene,s.rig,s.prop,s.bone,s.start,s.end)
            s.status='已创建 '+action.name+'；释放后保持最后位置'
        except (ValueError,RuntimeError) as e:self.report({'ERROR'},str(e));return {'CANCELLED'}
        return {'FINISHED'}


class BAW_OT_prop_restore(bpy.types.Operator):
    bl_idname='baw.prop_restore';bl_label='恢复道具原状态';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:restore_prop_contact(context.scene.baw_finishing.prop)
        except (ValueError,RuntimeError) as e:self.report({'ERROR'},str(e));return {'CANCELLED'}
        context.scene.baw_finishing.status='已恢复道具原状态'
        return {'FINISHED'}


class BAW_OT_inspect_motion(bpy.types.Operator):
    bl_idname='baw.inspect_motion';bl_label='检查停顿与速度'
    def execute(self,context):
        s=context.scene.baw_finishing
        try:report=inspect_motion(context.scene,s.rig,s.start,s.end,s.still_speed,s.min_hold)
        except (ValueError,RuntimeError) as e:self.report({'ERROR'},str(e));return {'CANCELLED'}
        text=bpy.data.texts.new('BAW_动作节奏检查');text.write(json.dumps(report,ensure_ascii=False,indent=2))
        s.status=f'发现 {len(report["low_speed_intervals"])} 个低速候选；详见文本：{text.name}'
        self.report({'INFO'},s.status);return {'FINISHED'}


class BAW_PT_finishing(bpy.types.Panel):
    bl_idname='BAW_PT_finishing';bl_label='道具接触与动作检查';bl_parent_id='BAW_PT_main'
    bl_category='BA 动画';bl_space_type='VIEW_3D';bl_region_type='UI';bl_options={'DEFAULT_CLOSED'}
    def draw(self,context):
        from .panels import _wrapped
        l=self.layout;s=context.scene.baw_finishing
        l.prop(s,'rig');row=l.row(align=True);row.prop(s,'start');row.prop(s,'end')
        box=l.box();box.prop(s,'prop')
        if s.rig:box.prop_search(s,'bone',s.rig.data,'bones')
        else:box.prop(s,'bone')
        _wrapped(box,context,'先在开始帧把道具对齐手；手的现有动作驱动道具。结束帧作为放下时刻。','INFO')
        box.operator('baw.prop_contact')
        action=s.prop.animation_data.action if s.prop and s.prop.animation_data else None
        row=box.row();row.enabled=bool(action and action.get('baw_contact_owner')==s.prop.name)
        row.operator('baw.prop_restore')
        if action and action.get('baw_contact_owner')!=s.prop.name:
            _wrapped(box,context,'该道具已有独立动画；本工具会保留它，不能直接覆盖。','INFO')
        box=l.box();box.prop(s,'still_speed');box.prop(s,'min_hold');box.operator('baw.inspect_motion')
        if s.status:_wrapped(l,context,s.status,'INFO')


CLASSES=(BAW_PG_finishing,BAW_OT_prop_contact,BAW_OT_prop_restore,BAW_OT_inspect_motion,BAW_PT_finishing)
def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Scene.baw_finishing=PointerProperty(type=BAW_PG_finishing)
def unregister():
    del bpy.types.Scene.baw_finishing
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
