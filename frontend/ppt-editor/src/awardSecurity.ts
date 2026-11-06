import DOMPurify from 'dompurify'
import { FONTS } from '@/configs/font'
function localFont(value:string){
 const names=value.replace(/[\"']/g,'').split(',').map(s=>s.trim())
 for(const name of names){const exact=FONTS.find(f=>f.value===name||f.label===name);if(exact)return exact.value;if(/^AC_[a-zA-Z0-9_]+$/.test(name))return name}
 const name=names.join(' ').toLowerCase()
 if(/仿宋|fangsong/.test(name))return 'AC_fangsong'
 if(/楷|kaiti|kai /.test(name))return 'AC_kai'
 if(/宋|simsun|song/.test(name))return 'AC_song'
 if(/times|serif/.test(name)&&!/sans/.test(name))return 'AC_liberationserif_regular'
 if(/courier|mono/.test(name))return 'AC_liberationmono_regular'
 if(/arial|calibri|sans/.test(name))return 'AC_liberationsans_regular'
 return 'AC_hei'
}
function cleanHTML(value:string){
 const html=DOMPurify.sanitize(value,{ALLOWED_TAGS:['p','span','strong','b','em','i','u','s','strike','sub','sup','br','ul','ol','li','blockquote','code'],ALLOWED_ATTR:['style','data-indent']})
 const template=document.createElement('template');template.innerHTML=html
 const allowed=new Set(['font-family','font-size','font-weight','font-style','text-decoration','text-decoration-line','color','background-color','text-align','text-indent','line-height','letter-spacing','vertical-align','padding-left','padding-right','margin-left','margin-right','white-space'])
 for(const el of template.content.querySelectorAll<HTMLElement>('[style]')){for(const property of Array.from(el.style))if(!allowed.has(property)||/url\s*\(|expression\s*\(|javascript\s*:/i.test(el.style.getPropertyValue(property)))el.style.removeProperty(property);if(el.style.fontFamily)el.style.fontFamily=localFont(el.style.fontFamily)}
 return template.innerHTML
}
export function sanitizeSlides(slides:any[]){
  if(!Array.isArray(slides)||!slides.length||slides.length>100)throw Error('导入文件需要1～100页')
  function visit(item:any,depth=0){
    if(depth>35)throw Error('模板层级过深')
    if(!item||typeof item!=='object')return
    for(const key of Object.keys(item)){
      const value=item[key]
      if(['__proto__','prototype','constructor'].includes(key))throw Error('模板属性无效')
      if(['content','text'].includes(key)&&typeof value==='string')item[key]=cleanHTML(value)
      else if(['fontName','defaultFontName','fontname'].includes(key)&&typeof value==='string')item[key]=localFont(value)
      else if(key==='link'&&value?.type==='web'&&!/^https?:\/\/[^\s<>]+$/i.test(value.target))throw Error('链接仅支持HTTP/HTTPS地址')
      else if(['src','poster','pattern'].includes(key)&&typeof value==='string'&&value&&!/^(data:(image|audio|video)\/|blob:)/i.test(value))throw Error('不允许外部媒体资源，请先下载后从本地导入')
      else visit(value,depth+1)
    }
  }
  visit(slides)
  if(slides.reduce((n,s)=>n+(s.elements?.length||0),0)>2000)throw Error('模板元素过多')
  return slides
}
export async function normalizeMedia(value:any):Promise<any>{
  if(value&&typeof value==='object')for(const key of Object.keys(value)){
    if(typeof value[key]==='string'&&value[key].startsWith('blob:')){
      const blob=await(await fetch(value[key])).blob()
      value[key]=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob)})
    }else if(value[key]&&typeof value[key]==='object')await normalizeMedia(value[key])
  }
  return value
}
