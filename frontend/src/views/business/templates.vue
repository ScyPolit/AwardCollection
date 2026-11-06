<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, type UploadFile } from "element-plus";
import { copyTemplate, createTemplate, listDepartments, listTemplates, publishTemplate, saveTemplateVersion, type Option, type Template } from "@/api/business";

type TextLayer = { id:string; type:"text"; field:string; text?:string; x:number; y:number; width:number; height:number; fontSize:number; minFontSize:number; color:string; align:string };
type SealLayer = { id:string; type:"seal"; department?:number; x:number; y:number; size:number };
type Layer = TextLayer | SealLayer;
type CanvasModel = { page:{width:number;height:number}; background:string; layers:Layer[]; watermark:boolean };

const rows=ref<Template[]>([]),departments=ref<Option[]>([]),selectedId=ref<number>(),selectedLayerId=ref("");
const canvas=ref<CanvasModel>({page:{width:842,height:595},background:"",layers:[],watermark:true});
const selectedTemplate=computed(()=>rows.value.find(item=>item.id===selectedId.value));
const selectedLayer=computed(()=>canvas.value.layers.find(item=>item.id===selectedLayerId.value));
const scale=computed(()=>Math.min(1,760/canvas.value.page.width));
const templateDialog=ref(false),templateSaving=ref(false);
const templateForm=reactive({name:"",department:undefined as number|undefined,copy:false});
let layerSequence=0;
function layerId(){return globalThis.crypto?.randomUUID?.()||`layer-${Date.now().toString(36)}-${++layerSequence}`}
let dragState:{layer:Layer;x:number;y:number;clientX:number;clientY:number;pointer:number;target:HTMLElement}|null=null;
function startDrag(layer:Layer,event:PointerEvent){
  if(event.button!==0)return;
  selectedLayerId.value=layer.id;
  const target=event.currentTarget as HTMLElement;
  target.setPointerCapture(event.pointerId);
  dragState={layer,x:layer.x,y:layer.y,clientX:event.clientX,clientY:event.clientY,pointer:event.pointerId,target};
}
function moveLayer(layer:Layer,x:number,y:number){
  const width=layer.type==="seal"?layer.size:layer.width;
  const height=layer.type==="seal"?layer.size:layer.height;
  layer.x=Math.round(Math.max(0,Math.min(canvas.value.page.width-width,x)));
  layer.y=Math.round(Math.max(0,Math.min(canvas.value.page.height-height,y)));
}
function moveDrag(event:PointerEvent){
  if(!dragState||dragState.pointer!==event.pointerId)return;
  moveLayer(dragState.layer,dragState.x+(event.clientX-dragState.clientX)/scale.value,dragState.y+(event.clientY-dragState.clientY)/scale.value);
}
function endDrag(event:PointerEvent){
  if(!dragState||dragState.pointer!==event.pointerId)return;
  if(dragState.target.hasPointerCapture(event.pointerId))dragState.target.releasePointerCapture(event.pointerId);
  dragState=null;
}
function moveByKey(layer:Layer,event:KeyboardEvent){
  const delta:Record<string,[number,number]>={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
  if(!delta[event.key])return;
  event.preventDefault();
  const [x,y]=delta[event.key],step=event.shiftKey?10:1;
  moveLayer(layer,layer.x+x*step,layer.y+y*step);
}
function openTemplateDialog(copy:boolean){Object.assign(templateForm,{copy,name:copy?`${selectedTemplate.value?.name||"模板"} 副本`:"新证书模板",department:departments.value[0]?.id});templateDialog.value=true}
async function createOrCopy(){
  if(!templateForm.department)return;
  templateSaving.value=true;
  try{
    const target=templateForm.copy&&selectedId.value
      ?await copyTemplate(selectedId.value,{name:templateForm.name,department:templateForm.department})
      :await createTemplate({name:templateForm.name,department:templateForm.department,published:true,canvas:normalize({})});
    if(!target.published)await publishTemplate(target.id);
    await load();selectedId.value=target.id;templateDialog.value=false;
    ElMessage.success("模板已保存到共享模板库");
  }finally{templateSaving.value=false}
}
const fieldLabels:Record<string,string>={static:"固定文本",team_name:"团队名称",members:"团队成员",award_name:"奖项",work_name:"作品名称",category:"项目类别",teachers:"指导教师",number:"证书编号"};

function normalize(raw:any):CanvasModel{
  if(raw?.layers)return {page:raw.page||{width:842,height:595},background:raw.background||"",layers:raw.layers,watermark:raw.watermark??raw.showWatermark??true};
  return {page:raw?.page||{width:842,height:595},background:raw?.background||"",watermark:raw?.watermark??raw?.showWatermark??true,layers:[
    {id:layerId(),type:"text",field:"static",text:raw?.title||"获 奖 证 书",x:110,y:90,width:622,height:60,fontSize:raw?.size||34,minFontSize:18,color:raw?.color||"#1f2937",align:"center"},
    {id:layerId(),type:"text",field:"team_name",x:110,y:190,width:622,height:65,fontSize:22,minFontSize:11,color:"#1f2937",align:"center"},
    {id:layerId(),type:"text",field:"award_name",x:110,y:280,width:622,height:50,fontSize:18,minFontSize:10,color:"#1f2937",align:"center"},
    ...(raw?.number===false||raw?.showNumber===false?[]:[{id:layerId(),type:"text" as const,field:"number",x:72,y:500,width:320,height:24,fontSize:11,minFontSize:9,color:"#4b5563",align:"left"}])
  ]};
}
async function load(){[rows.value,departments.value]=await Promise.all([listTemplates(),listDepartments()]);if(!selectedId.value&&rows.value.length)selectedId.value=rows.value[0].id}
watch(selectedTemplate,item=>{canvas.value=normalize(item?.latest_version?.canvas);selectedLayerId.value=canvas.value.layers[0]?.id||""});
function addText(){const layer:TextLayer={id:layerId(),type:"text",field:"static",text:"新文本",x:160,y:130,width:520,height:55,fontSize:24,minFontSize:10,color:"#1f2937",align:"center"};canvas.value.layers.push(layer);selectedLayerId.value=layer.id}
function addSeal(){const layer:SealLayer={id:layerId(),type:"seal",department:departments.value[0]?.id,x:620,y:410,size:100};canvas.value.layers.push(layer);selectedLayerId.value=layer.id}
function remove(){canvas.value.layers=canvas.value.layers.filter(item=>item.id!==selectedLayerId.value);selectedLayerId.value=canvas.value.layers[0]?.id||""}
function upload(file:UploadFile){if(!file.raw)return;const reader=new FileReader();reader.onload=()=>canvas.value.background=String(reader.result);reader.readAsDataURL(file.raw)}
async function save(){if(!selectedId.value)return;const result=await saveTemplateVersion(selectedId.value,canvas.value);ElMessage.success(`已保存模板版本 v${result.number}`);await load()}
function sample(layer:Layer){if(layer.type==="seal")return "公章";return layer.field==="static"?layer.text:({team_name:"测试专用团队",members:"张三、李四",award_name:"一等奖",work_name:"测试专用作品",category:"创新类",teachers:"王老师",number:"2026-AC-00000001"} as any)[layer.field]}
onMounted(load);
</script>
<template><div class="editor"><aside><h3>模板</h3><el-button class="full" @click="openTemplateDialog(false)">新建模板</el-button><el-button class="full" :disabled="!selectedId" @click="openTemplateDialog(true)">复制当前模板</el-button><el-select v-model="selectedId" class="full"><el-option v-for="t in rows" :key="t.id" :label="`${t.name} · ${t.department_name}`" :value="t.id"/></el-select><el-divider/><h3>图层</h3><el-button class="full" @click="addText">添加文本</el-button><el-upload :auto-upload="false" :show-file-list="false" accept="image/*" :on-change="upload"><el-button class="full">上传背景</el-button></el-upload><el-button class="full" @click="addSeal">添加公章位</el-button><div class="layers"><button v-for="layer in canvas.layers" :key="layer.id" :class="{active:selectedLayerId===layer.id}" @click="selectedLayerId=layer.id">{{layer.type==='seal'?'公章位':fieldLabels[layer.field]}}</button></div></aside><main><div class="canvas-wrap" :style="{width:canvas.page.width*scale+'px',height:canvas.page.height*scale+'px'}"><div class="canvas" :style="{width:canvas.page.width+'px',height:canvas.page.height+'px',transform:`scale(${scale})`,backgroundImage:canvas.background?`url(${canvas.background})`:''}"><div v-for="layer in canvas.layers" :key="layer.id" class="layer" :class="{selected:selectedLayerId===layer.id,seal:layer.type==='seal'}" :style="layer.type==='text'?{left:layer.x+'px',top:layer.y+'px',width:layer.width+'px',height:layer.height+'px',fontSize:layer.fontSize+'px',color:layer.color,textAlign:layer.align as any}:{left:layer.x+'px',top:layer.y+'px',width:layer.size+'px',height:layer.size+'px'}" @pointerdown.stop.prevent="startDrag(layer,$event)" @pointermove.stop="moveDrag" @pointerup="endDrag" @pointercancel="endDrag" @keydown="moveByKey(layer,$event)" tabindex="0" role="button" :aria-label="layer.type==='seal'?'公章图层':fieldLabels[layer.field]+'图层'" @click.stop="selectedLayerId=layer.id">{{sample(layer)}}</div><small v-if="canvas.watermark" class="watermark">2026-AC-00000001</small></div></div></main><aside><h3>属性</h3><template v-if="selectedLayer"><el-form label-position="top"><template v-if="selectedLayer.type==='text'"><el-form-item label="内容类型"><el-select v-model="selectedLayer.field" class="full"><el-option v-for="(label,key) in fieldLabels" :key="key" :label="label" :value="key"/></el-select></el-form-item><el-form-item v-if="selectedLayer.field==='static'" label="固定文本"><el-input v-model="selectedLayer.text"/></el-form-item><el-form-item label="字号"><el-input-number v-model="selectedLayer.fontSize" :min="8" :max="72"/></el-form-item><el-form-item label="最小字号"><el-input-number v-model="selectedLayer.minFontSize" :min="6" :max="selectedLayer.fontSize"/></el-form-item><el-form-item label="颜色"><el-color-picker v-model="selectedLayer.color"/></el-form-item><el-form-item label="对齐"><el-segmented v-model="selectedLayer.align" :options="[{label:'左',value:'left'},{label:'中',value:'center'},{label:'右',value:'right'}]"/></el-form-item><el-form-item label="位置与区域"><div class="coords"><el-input-number v-model="selectedLayer.x"/><el-input-number v-model="selectedLayer.y"/><el-input-number v-model="selectedLayer.width"/><el-input-number v-model="selectedLayer.height"/></div></el-form-item></template><template v-else><el-form-item label="对应部门"><el-select v-model="selectedLayer.department" class="full"><el-option v-for="d in departments" :key="d.id" :label="d.name" :value="d.id"/></el-select></el-form-item><el-form-item label="位置与尺寸"><div class="coords"><el-input-number v-model="selectedLayer.x"/><el-input-number v-model="selectedLayer.y"/><el-input-number v-model="selectedLayer.size"/></div></el-form-item></template><el-button type="danger" plain class="full" @click="remove">删除图层</el-button></el-form></template><el-divider/><el-checkbox v-model="canvas.watermark">显示编号水印</el-checkbox><el-button type="primary" class="full save" :disabled="!selectedId" @click="save">保存新版本</el-button></aside><el-dialog v-model="templateDialog" :title="templateForm.copy?'复制模板':'新建模板'" width="480"><el-form label-position="top"><el-form-item label="模板名称"><el-input v-model="templateForm.name"/></el-form-item><el-form-item label="维护部门"><el-select v-model="templateForm.department" class="full"><el-option v-for="d in departments" :key="d.id" :label="d.name" :value="d.id"/></el-select></el-form-item></el-form><template #footer><el-button @click="templateDialog=false">取消</el-button><el-button type="primary" :loading="templateSaving" :disabled="!templateForm.name.trim()||!templateForm.department" @click="createOrCopy">保存到模板库</el-button></template></el-dialog></div></template>
<style scoped>.editor{display:grid;grid-template-columns:230px 1fr 280px;height:calc(100vh - 110px);background:#f5f7fa}.editor aside{background:#fff;padding:18px;border-right:1px solid #e5e7eb;overflow:auto}.editor aside:last-child{border:0;border-left:1px solid #e5e7eb}.editor main{display:grid;place-items:center;overflow:auto;padding:24px}.canvas-wrap{position:relative}.canvas{position:absolute;left:0;top:0;transform-origin:top left;background:#fff center/cover no-repeat;border:1px solid #cfd4dc;box-shadow:0 8px 24px rgb(0 0 0 / 8%);overflow:hidden}.layer{cursor:grab;touch-action:none;user-select:none;position:absolute;display:flex;align-items:center;justify-content:center;border:1px dashed transparent;line-height:1.35;overflow:hidden}.layer:active{cursor:grabbing}.layer:focus-visible{outline:2px solid #409eff}.layer.selected{border-color:#409eff;background:rgb(64 158 255 / 5%)}.layer.seal{border:2px dashed #dc2626;border-radius:50%;color:#dc2626;font-size:16px}.watermark{position:absolute;right:60px;bottom:28px;color:#aaa}.full{width:100%;margin-bottom:10px}.layers{border-top:1px solid #ebeef5;margin-top:8px;padding-top:8px}.layers button{display:block;width:100%;border:0;background:transparent;text-align:left;padding:8px;color:#606266}.layers button.active{background:#ecf5ff;color:#409eff}.coords{display:grid;grid-template-columns:1fr 1fr;gap:8px}.save{margin-top:18px}:deep(.el-upload){width:100%}@media(max-width:900px){.editor{grid-template-columns:1fr;height:auto}.editor aside{border:0;border-bottom:1px solid #ddd}.editor main{min-height:420px}}</style>
