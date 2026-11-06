import { FONTS } from '@/configs/font'

export const fields = [
  {label:'团队成员',value:'members'},{label:'团队名称',value:'team_name'},
  {label:'奖项',value:'award_name'},{label:'作品名称',value:'work_name'},
  {label:'项目类别',value:'category'},{label:'指导教师',value:'teachers'},
  {label:'证书编号',value:'number'},{label:'竞赛名称',value:'competition_name'},
  {label:'颁发日期',value:'issue_date'},
]
export const sample:Record<string,string>={members:'张三、李四',team_name:'示例团队',award_name:'一等奖',work_name:'示例作品',category:'创新类',teachers:'王老师',number:'PREVIEW-ONLY',competition_name:'校赛',issue_date:'2026-11-06'}
export function fontFamily(id:string){return 'AC_'+id.replaceAll('-','_')}
export function registerFonts(fonts:Array<{id:string;name?:string;family?:string;url:string}>){
  FONTS.splice(0,FONTS.length,...fonts.map(f=>({label:f.name||f.id,value:f.family||fontFamily(f.id)})))
  for(const f of fonts){
    const family=f.family||fontFamily(f.id)
    if(![...document.fonts].some(face=>face.family===family)) (document.fonts as FontFaceSet&{add(face:FontFace):void}).add(new FontFace(family,`url("${f.url}")`))
  }
}
export function escape(value:unknown){return String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')}
export function placeholder(department?:number,name='公章位'){
  return 'data:image/svg+xml;base64,'+btoa(unescape(encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><circle cx="60" cy="60" r="56" fill="none" stroke="#d34a4a" stroke-dasharray="5 4"/><text x="60" y="58" font-size="13" text-anchor="middle" fill="#d34a4a">${escape(name)}</text><text x="60" y="78" font-size="10" text-anchor="middle" fill="#d34a4a">部门 ${department||''}</text></svg>`)))
}
export function legacyDocument(canvas:any,title:string){
  const page=canvas.page||{width:842,height:595}
  const layers=canvas.layers||[
    {id:'title',type:'text',field:'static',text:canvas.title||'获 奖 证 书',x:110,y:90,width:622,height:60,fontSize:34,fontFamily:'hei',align:'center'},
    {id:'team',type:'text',field:'team_name',x:110,y:190,width:622,height:65,fontSize:22,fontFamily:'hei',align:'center'},
    {id:'award',type:'text',field:'award_name',x:110,y:280,width:622,height:50,fontSize:18,fontFamily:'hei',align:'center'},
  ]
  const elements:any[]=[]
  for(const [index,layer] of layers.entries()){
    const id=layer.id||`legacy-${index}`
    if(layer.type==='text'){
      const family=fontFamily(layer.fontFamily||'hei'),value=layer.field==='static'?layer.text:`{{${layer.field}}}`
      const style=`font-family:${family};font-size:${layer.fontSize||24}px;color:${layer.color||'#1f2937'};font-weight:${layer.bold?'bold':'normal'};font-style:${layer.italic?'italic':'normal'};text-decoration:${layer.underline?'underline':'none'}`
      elements.push({id,type:'text',left:layer.x,top:layer.y,width:layer.width||680,height:layer.height||70,rotate:0,defaultFontName:family,defaultColor:layer.color||'#1f2937',lineHeight:layer.lineHeight||1.35,paragraphSpace:0,inset:[0,0,0,0],fixedHeight:true,vAlign:'top',awardAutoFit:layer.field!=='static',content:`<p style="text-align:${layer.align||'center'}"><span style="${style}">${escape(value)}</span></p>`})
    }
    else if(layer.type==='seal') elements.push({id,type:'image',left:layer.x,top:layer.y,width:layer.size||100,height:layer.size||100,rotate:0,fixedRatio:true,src:placeholder(layer.department),awardSealDepartment:layer.department})
    else if(layer.type==='shape'){
      const w=layer.width,h=layer.height,p=(layer.strokeWidth||0)/2
      let shape=''
      if(layer.kind==='rect')shape=`<rect x="${p}" y="${p}" width="${w-2*p}" height="${h-2*p}"/>`
      else if(layer.kind==='ellipse')shape=`<ellipse cx="${w/2}" cy="${h/2}" rx="${w/2-p}" ry="${h/2-p}"/>`
      else shape=`<polyline points="${(layer.points||[]).map((pt:number[])=>`${p+pt[0]*(w-2*p)},${p+pt[1]*(h-2*p)}`).join(' ')}" fill="none"/>`
      const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" stroke="${layer.stroke||'#1f2937'}" stroke-width="${layer.strokeWidth||0}" fill="${layer.fill||'none'}" stroke-linecap="round" stroke-linejoin="round">${shape}</svg>`
      elements.push({id,type:'image',left:layer.x,top:layer.y,width:w,height:h,rotate:0,fixedRatio:false,src:'data:image/svg+xml;base64,'+btoa(unescape(encodeURIComponent(svg)))})
    }
  }
  if(canvas.watermark??canvas.showWatermark??false)elements.push({id:'award-watermark',type:'text',left:page.width-360,top:page.height-48,width:300,height:20,rotate:0,defaultFontName:'AC_hei',defaultColor:'#bfbfbf',inset:[0,0,0,0],content:'<p style="text-align:right;font-size:9px">{{number}}</p>'})
  return {title,viewportSize:page.width,viewportRatio:page.height/page.width,theme:{fontName:'AC_hei',fontColor:'#1f2937',backgroundColor:'#fff',themeColors:['#409eff','#1f4b73','#c53030'],outline:{width:2,color:'#525252',style:'solid'},shadow:{h:3,v:3,blur:2,color:'#808080'}},slides:[{id:'certificate',elements,background:canvas.background?{type:'image',image:{src:canvas.background,size:'100% 100%'}}:{type:'solid',color:'#fff'}}]}
}
