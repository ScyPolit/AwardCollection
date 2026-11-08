<script setup lang="ts">
import {ref} from 'vue'
import {useMainStore,useSlidesStore,useSnapshotStore} from '@/store'
import {nanoid} from 'nanoid'
import {fields,escape,placeholder} from './award'
import Button from '@/components/Button.vue'
import message from '@/utils/message'
const binding=ref('members'),department=ref(''),main=useMainStore(),slides=useSlidesStore()
const context=(window as any).__AWARD_CONTEXT__||{}
function addField(){
  const current=main.handleElement
  if(current?.type==='text')slides.updateElement({id:current.id,props:{content:`<p><span style="font-family:AC_hei;font-size:24px">{{${binding.value}}}</span></p>`}})
  else slides.addElement({id:nanoid(10),type:'text',left:80,top:180,width:600,height:75,rotate:0,content:`<p><span style="font-family:AC_hei;font-size:24px">{{${binding.value}}}</span></p>`,defaultFontName:'AC_hei',defaultColor:'#1f2937',inset:[0,0,0,0],fixedHeight:true} as any)
  useSnapshotStore().addSnapshot()
}
function addSeal(){
  const id=Number(department.value);if(!id)return message.error('请选择盖章部门')
  const label=context.departments?.find((d:any)=>d.id===id)?.name||'公章位'
  slides.addElement({id:nanoid(10),type:'image',left:slides.viewportSize-220,top:slides.viewportSize*slides.viewportRatio-170,width:119,height:119,rotate:0,fixedRatio:true,src:placeholder(id,label),awardSealDepartment:id} as any)
  useSnapshotStore().addSnapshot()
}
function save(){window.dispatchEvent(new Event('award-save'))}
function preview(){window.parent.postMessage({type:'award-preview'},location.origin)}
</script>
<template>
  <div class="award-controls">
    <select v-model="binding" aria-label="证书字段"><option v-for="field in fields" :key="field.value" :value="field.value">{{field.label}}</option></select><Button @click="addField">插入字段</Button>
    <select v-model="department" aria-label="盖章部门"><option value="">选择盖章部门</option><option v-for="d in context.departments||[]" :key="d.id" :value="String(d.id)">{{d.name}}</option></select><Button @click="addSeal">添加公章位</Button>
    <Button @click="preview">证书预览</Button><Button type="primary" @click="save">保存模板</Button>
  </div>
</template>
<style scoped>.award-controls{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.award-controls select{max-width:140px;height:30px;padding:0 6px;border:1px solid #d9d9d9;border-radius:2px;background:var(--ppt-panel,#fff);color:inherit}</style>
