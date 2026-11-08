import { createApp, h, ref, nextTick } from 'vue'
import { createPinia } from 'pinia'
import { useSlidesStore } from '@/store'
import ThumbnailSlide from '@/views/components/ThumbnailSlide/index.vue'
import { registerFonts } from './award'
import 'prosemirror-view/style/prosemirror.css'
import '@/assets/styles/prosemirror.scss'
import '@/assets/styles/global.scss'

const slide=ref<any>(),size=ref(1000)
const app=createApp({render:()=>slide.value?h(ThumbnailSlide,{slide:slide.value,size:size.value}):null})
app.use(createPinia());app.mount('#app')
let fontCoverage=new Map<string,Set<number>>()
let original:Array<{el:HTMLElement;html:string;id:string;autoFit:boolean;tokens:string[]}>=[]
let preflightCache=new Map<string,Set<string>>()
function replaceTokens(el:HTMLElement,values:Record<string,string>){
  const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),nodes:Text[]=[]
  let current:Node|null;while((current=walker.nextNode()))nodes.push(current as Text)
  const text=nodes.map(n=>n.data).join(''),matches=[...text.matchAll(/\{\{([a-z_]+)\}\}/g)].reverse()
  for(const match of matches){
    if(!(match[1] in values))throw Error(`未知证书字段：${match[1]}`)
    const start=match.index!,end=start+match[0].length
    let offset=0,startNode:Text|undefined,endNode:Text|undefined,startOffset=0,endOffset=0
    for(const node of nodes){const limit=offset+node.data.length;if(!startNode&&start>=offset&&start<limit){startNode=node;startOffset=start-offset}if(end>offset&&end<=limit){endNode=node;endOffset=end-offset;break}offset=limit}
    if(startNode&&endNode){const range=document.createRange();range.setStart(startNode,startOffset);range.setEnd(endNode,endOffset);range.deleteContents();range.insertNode(document.createTextNode(String(values[match[1]]??'')))}
  }
}
(window as any).certLoad=async(payload:any)=>{
  registerFonts(payload.fonts)
  fontCoverage=new Map(payload.fonts.map((f:any)=>[f.family,new Set<number>(f.coverage||[])]))
  const canvas=payload.canvas,doc=canvas.presentation,store=useSlidesStore()
  store.setViewportSize(doc.viewportSize);store.setViewportRatio(doc.viewportRatio);store.setTheme(doc.theme||{})
  slide.value=structuredClone(doc.slides[canvas.slideIndex||0]);size.value=doc.viewportSize
  const images=new Map((payload.seals||[]).map((s:any)=>[s.department_id,s.src]))
  const slots=new Set(slide.value.elements.filter((e:any)=>e.awardSealDepartment).map((e:any)=>e.awardSealDepartment))
  for(const seal of payload.seals||[])if(!slots.has(seal.department_id))throw Error(`模板缺少部门${seal.department_id}的公章位`)
  for(const element of slide.value.elements)if(element.awardSealDepartment&&images.size)element.src=images.get(element.awardSealDepartment)||'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4//8/AwAI/AL+XFLPAAAAAElFTkSuQmCC'
  document.documentElement.style.width=canvas.page.width*4/3+'px';document.documentElement.style.height=canvas.page.height*4/3+'px'
  document.body.style.margin='0';document.body.style.overflow='hidden'
  const style=document.getElementById('print-style')||Object.assign(document.createElement('style'),{id:'print-style'})
  style.textContent=`@page{size:${canvas.page.width}pt ${canvas.page.height}pt;margin:0}html,body{padding:0;margin:0}#app{width:${doc.viewportSize}px;transform:scale(${canvas.page.width/doc.viewportSize*4/3});transform-origin:0 0}.ProseMirror-static{white-space:break-spaces!important}*{animation:none!important;transition:none!important;print-color-adjust:exact!important;-webkit-print-color-adjust:exact!important}`
  document.head.append(style);await nextTick()
  await Promise.all(payload.fonts.map(async(f:any)=>{await document.fonts.load(`16px "${f.family}"`)}))
  await Promise.all([...document.images].map(img=>img.complete?(img.naturalWidth?Promise.resolve():Promise.reject(Error('模板图片无法加载'))):new Promise<void>((resolve,reject)=>{img.onload=()=>resolve();img.onerror=()=>reject(Error('模板图片无法加载'))})))
  for(const el of document.querySelectorAll<HTMLElement>('[style]'))if(/AC_/.test(el.style.fontFamily))el.style.fontFamily+=', AC_hei'
  original=[]
  for(const element of slide.value.elements){
    for(const el of document.querySelectorAll<HTMLElement>(`.base-element-${CSS.escape(element.id)} .ProseMirror-static, .base-element-${CSS.escape(element.id)} .cell-text`))original.push({el,html:el.innerHTML,id:element.id,autoFit:element.awardAutoFit!==false,tokens:[...new Set([...el.textContent?.matchAll(/\{\{([a-z_]+)\}\}/g)||[]].map(match=>match[1]))]})
  }
  ;(window as any).__CERT_APP_READY__=true
}
(window as any).certFill=async(values:Record<string,string>,preflight=false)=>{
  const keys=preflight?new Map(original.map(item=>[item,JSON.stringify(item.tokens.map(key=>[key,values[key]]))])):new Map()
  const targets=preflight?original.filter(item=>!preflightCache.get(item.id+'|'+item.html)?.has(keys.get(item)!)):original
  for(const item of targets){item.el.innerHTML=item.html;replaceTokens(item.el,values)}
  await document.fonts.ready
  for(const item of targets){
    const walker=document.createTreeWalker(item.el,NodeFilter.SHOW_TEXT);let node:Node|null
    while((node=walker.nextNode())){
      const family=getComputedStyle(node.parentElement!).fontFamily.match(/AC_[a-zA-Z0-9_]+/)?.[0]||'AC_hei'
      const selected=fontCoverage.get(family),fallback=fontCoverage.get('AC_hei')
      if(!selected?.size)continue
      for(const character of node.textContent||'')if(!/\s/.test(character)&&!selected.has(character.codePointAt(0)!)&&!fallback?.has(character.codePointAt(0)!))throw Error(`字体缺少字形“${character}”，请导入支持该字符的字体`)
    }
  }
  for(const item of targets){
    if(!/\{\{[a-z_]+\}\}/.test(item.html)||item.el.classList.contains('cell-text'))continue
    const element=slide.value.elements.find((e:any)=>e.id===item.id),inset=element.inset||[10,10,10,10],available=element.height-inset[0]-inset[2]
    const nodes=[item.el,...item.el.querySelectorAll<HTMLElement>('[style]')]
    const sizes=nodes.map(el=>parseFloat(getComputedStyle(el).fontSize)||16)
    let factor=1
    while(item.el.scrollHeight>available+1&&item.autoFit&&Math.min(...sizes)*factor>6){factor-=.03;nodes.forEach((el,i)=>el.style.fontSize=Math.max(6,sizes[i]*factor)+'px')}
    if(item.el.scrollHeight>available+1||item.el.scrollWidth>element.width-inset[1]-inset[3]+1)throw Error(`字段文本超出文本框：${element.name||element.id}，请扩大文本框或减小字号`)
  }
  if(preflight)for(const item of targets){const key=item.id+'|'+item.html,cache=preflightCache.get(key)||new Set<string>();if(cache.size<10000)cache.add(keys.get(item)!);preflightCache.set(key,cache)}
  return true
}
(window as any).certPreflight=async(rows:Array<{source_row:number;values:Record<string,string>}>)=>{
  preflightCache.clear()
  const start=performance.now(),errors:any[]=[]
  for(const row of rows){try{await (window as any).certFill(row.values,true)}catch(error){errors.push({row:row.source_row,error:String(error)});if(errors.length>=20)break}if(performance.now()-start>80000)throw Error('名单预检耗时过长，请拆分批次')}
  return errors
}
