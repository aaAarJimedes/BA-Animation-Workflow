"""Exercise transactions, shape animation, shared data and artist correction."""
import sys,json
from pathlib import Path
import bpy,bmesh
from mathutils import Vector
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'extension'))
import ba_animation_workflow as addon
addon.register()
from ba_animation_workflow import parts,parts_ui
out=Path('D:/Agent Workspaces/Agent Temp/BA_Animation_Workflow/testing/parts');out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
arm=bpy.data.armatures.new('Rig');rig=bpy.data.objects.new('Rig',arm);scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
bone=arm.edit_bones.new('root');bone.head=(0,0,0);bone.tail=(0,0,1)
bpy.ops.object.mode_set(mode='OBJECT');rig.select_set(False)
verts=[];faces=[];mats=[]
def box(center,size,mat):
 start=len(verts)
 verts.extend(tuple(center[a]+sign[a]*size[a]/2 for a in range(3)) for sign in [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),(1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)])
 faces.extend(tuple(start+i for i in f) for f in [(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6)])
 mats.extend([mat]*6)
box((0,0,.9),(.12,.12,1.8),0)
box((0,0,1.25),(.4,.2,.6),1)
box((-.35,0,1.35),(.3,.18,.18),1);box((.35,0,1.35),(.3,.18,.18),1)
for x in [-.25,.25]:
 box((x,0,.09),(.16,.25,.1),2)
 box((x,0,.035),(.16,.25,.02),3)
 box((x,-.13,.11),(.1,.015,.01),4)
box((.6,.3,1.1),(.05,.05,.05),5)
mesh=bpy.data.meshes.new('fixture');mesh.from_pydata(verts,[],faces);mesh.update()
obj=bpy.data.objects.new('Avatar',mesh);scene.collection.objects.link(obj)
for n in ['skin','jacket','shoe_upper','rubber_sole','shoelace','unknown']:
 mat=bpy.data.materials.new(n);mesh.materials.append(mat)
for p,m in zip(mesh.polygons,mats):p.material_index=m
uv=mesh.uv_layers.new(name='UVMap')
for i,item in enumerate(uv.uv):item.vector=(i%7/7,i%11/11)
mesh.normals_split_custom_set([tuple(n.vector) for n in mesh.corner_normals])
group=obj.vertex_groups.new(name='root');group.add(list(range(len(verts))),1,'REPLACE')
modifier=obj.modifiers.new('Skin','ARMATURE');modifier.object=rig
obj.shape_key_add(name='Basis');key=obj.shape_key_add(name='Bend')
for v in key.data:v.co.x+=v.co.z*.025
key.value=0;key.keyframe_insert('value',frame=1);key.value=.7;key.keyframe_insert('value',frame=20)
driverkey=obj.shape_key_add(name='Driver')
for v in driverkey.data:v.co.y+=.003
obj['amount']=.4;curve=driverkey.driver_add('value');var=curve.driver.variables.new();var.name='amount';var.type='SINGLE_PROP';var.targets[0].id=obj;var.targets[0].data_path='["amount"]';curve.driver.expression='amount'
shared=bpy.data.objects.new('Shared data sentinel',mesh);scene.collection.objects.link(shared);shared.hide_set(True);shared.hide_render=True
obj.select_set(True);bpy.context.view_layer.objects.active=obj
s=scene.baw_parts;s.target=obj
assert bpy.ops.baw.parts_analyze()=={'FINISHED'}
groups={p.group_id:p.faces for p in s.groups}
assert groups[3]==18 and groups[4]==18 and groups[5]==18,groups
assert groups[0]==6 and groups[1]==6,groups
original=parts.fingerprint(obj);counts=(len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.materials),len(bpy.data.actions))
# Preview cannot change shared geometry or object-level material overrides.
obj.material_slots[0].link='OBJECT';override=bpy.data.materials.new('skin_override');obj.material_slots[0].material=override
assert bpy.ops.baw.parts_analyze()=={'FINISHED'}
original=parts.fingerprint(obj);counts=(len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.materials),len(bpy.data.actions))
assert bpy.ops.baw.parts_preview()=={'FINISHED'}
assert shared.data is mesh and obj.data is mesh and obj.material_slots[0].material==override
assert bpy.ops.baw.parts_preview()=={'FINISHED'}
assert counts==(len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.materials),len(bpy.data.actions))
# Stale topology/coordinates are rejected before any extraction writes.
sources=parts_ui.source_data(s);mesh.vertices[0].co.x+=.1
try:parts.extract(bpy.context,sources,parts_ui.names_for(s),{3})
except ValueError:pass
else:raise AssertionError('stale plan accepted')
mesh.vertices[0].co.x-=.1
assert bpy.ops.baw.parts_analyze()=={'FINISHED'}
# Select all grouped sleeves/body, then deliberately remove one face and replace.
s.active=next(i for i,p in enumerate(s.groups) if p.group_id==3)
assert bpy.ops.baw.parts_select()=={'FINISHED'}
bm=bmesh.from_edit_mesh(mesh);bm.faces.ensure_lookup_table()
selected=[f for f in bm.faces if f.select];assert len(selected)==18,len(selected)
removed=selected[0].index;selected[0].select_set(False);bmesh.update_edit_mesh(mesh)
assert bpy.ops.baw.parts_assign(replace=True)=={'FINISHED'}
assert json.loads(s.sources[0].labels)[removed]==0
assert s.groups[s.active].faces==17
# Re-analyze to restore automatic grouping. Failure during validation rolls back
# every temporary result, while source/linked users stay intact.
assert bpy.ops.baw.parts_analyze()=={'FINISHED'}
counts=(len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.materials),len(bpy.data.actions));sources=parts_ui.source_data(s)
verify=parts.verify_piece
def fail(*args):raise RuntimeError('injected verification failure')
parts.verify_piece=fail
try:parts.extract(bpy.context,sources,parts_ui.names_for(s),{3,4,5})
except RuntimeError:pass
else:raise AssertionError('failed transaction succeeded')
finally:parts.verify_piece=verify
assert counts==(len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.materials),len(bpy.data.actions))
assert obj.data is shared.data
assert bpy.ops.baw.parts_extract()=={'FINISHED'}
pieces=list(s.result.all_objects)
assert len(pieces)==4
# Prove evaluated shape-key action + self-property driver + armature deformation.
max_difference=0
for frame in [1,11,20]:
 scene.frame_set(frame);rig.pose.bones['root'].rotation_mode='XYZ';rig.pose.bones['root'].rotation_euler.z=.1*frame/20
 bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
 # The hidden original must be evaluated for this diagnostic only.
 obj.hide_viewport=False;obj.hide_set(False);bpy.context.view_layer.update();ev=obj.evaluated_get(dg)
 for piece in pieces:
  target=piece.evaluated_get(dg)
  for v,source_id in zip(target.data.vertices,piece.data.attributes[parts.VERT_ID].data):
   difference=(v.co-ev.data.vertices[source_id.value].co).length;max_difference=max(max_difference,difference)
assert max_difference<1e-5,max_difference
assert shared.data==mesh
assert bpy.ops.baw.parts_switch()=={'FINISHED'}
# Linked-library style data and non-armature topology modifiers fail explicitly.
sub=obj.modifiers.new('Subdivision','SUBSURF')
try:parts.extract(bpy.context,parts_ui.source_data(s),parts_ui.names_for(s),{3})
except ValueError:pass
else:raise AssertionError('unsupported modifier accepted')
obj.modifiers.remove(sub)
# Distinct source meshes keep their own shape-key systems while belonging to
# the same garment collection. Also exercise a simple shape-key NLA clip.
ad=mesh.shape_keys.animation_data;action=ad.action;slot=ad.action_slot
ad.action=None;track=ad.nla_tracks.new();strip=track.strips.new('Shape clip',1,action);strip.action_slot=slot
extra_mesh=bpy.data.meshes.new('Separate garment fitting')
extra_mesh.from_pydata([(-.1,0,1.4),(.1,0,1.4),(0,.05,1.5)],[],[(0,1,2)]);extra_mesh.materials.append(mesh.materials[1])
extra=bpy.data.objects.new('Jacket fitting',extra_mesh);scene.collection.objects.link(extra)
extra.vertex_groups.new(name='root').add([0,1,2],1,'REPLACE');extra.modifiers.new('Skin','ARMATURE').object=rig
extra.shape_key_add(name='Basis');extra.shape_key_add(name='Unique fitting shape')
collection,multi=parts.extract(bpy.context,parts_ui.source_data(s)+[(extra,parts.fingerprint(extra),[3])],parts_ui.names_for(s),{3})
garment=next(c for c in collection.children if c.name.startswith('服装'))
assert len(garment.objects)==2
assert sorted(len(o.data.shape_keys.key_blocks) for o in garment.objects)==[2,3]
old_part=next(o for o in multi if o['baw_part_source']==obj.name)
assert old_part.data.shape_keys.animation_data.nla_tracks[0].strips[0].action==action
parts.discard(collection);ad.nla_tracks.remove(track);ad.action=action;ad.action_slot=slot
addon.unregister();addon.register()
report={'semantic_fixture':True,'shared_mesh_and_object_materials':True,'preview_no_leaks':True,'stale_guard':True,'manual_replace':True,'rollback':True,'shape_action_and_self_driver':True,'maximum_evaluated_deformation_difference':max_difference,'unsupported_modifier_guard':True,'multiple_source_meshes_one_garment':True,'simple_shape_nla':True,'register_cycle':True}
(out/'synthetic_report.json').write_text(json.dumps(report,indent=2),encoding='utf8');print('PARTS_SYNTHETIC_OK',report)
