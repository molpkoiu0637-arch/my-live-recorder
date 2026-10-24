import os, re, subprocess, threading, uuid, requests
from flask import Flask, request, jsonify
from datetime import datetime
app=Flask(__name__)
RECORD_DIR="/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs={}
HTML_PAGE = """
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>BIGO V15 CLIENT</title>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<style>body{background:#111;color:#fff;font-family:system-ui;padding:18px}input,select,button,textarea{width:100%;padding:14px;margin:8px 0;border-radius:12px;border:none;font-size:15px;box-sizing:border-box}button{background:#22c55e;color:#000;font-weight:bold}button.orange{background:#f59e0b}.card{background:#1e1e1e;border-radius:16px;padding:14px;margin:12px 0;border-left:4px solid #22c55e}.card.error{border-color:#ef4444}.card.done{border-color:#22c55e}pre{background:#000;padding:10px;border-radius:8px;overflow:auto;white-space:pre-wrap;font-size:11px;max-height:500px}.ok{color:#22c55e;font-weight:bold}video{width:100%;border-radius:12px;background:#000;margin:8px 0}</style>
</head><body>
<h2>BIGO V15 <span style="background:#22c55e;color:#000;padding:4px 10px;border-radius:20px;font-size:12px">CLIENT EXTRACT</span></h2>
<p style="color:#aaa;font-size:13px">แก้ IP Block โดยให้มือถือไทยแกะ HLS ก่อน แล้วส่งให้ Server อัด</p>

<input id="url" placeholder="วาง slink.bigovideo.tv/xxxx">
<button class="orange" onclick="extractClient()">ขั้นตอน 1: แกะลิงก์ HLS ด้วยเน็ตไทย (กดตรงนี้)</button>
<textarea id="hls" rows="3" placeholder="HLS จะขึ้นตรงนี้อัตโนมัติหลังแกะได้"></textarea>
<video id="video" controls muted></video>
<select id="q"><option>best</option><option>720p</option><option>480p SD</option></select>
<button onclick="startRecord()">ขั้นตอน 2: ส่ง HLS ให้ Server บันทึก</button>
<div id="status" class="ok"></div>
<div id="list"></div>

<script>
let foundHls="";
function extractUrl(t){let m=t.match(/https?:\\/\\/[^\\s]+/);if(m) return m[0].replace(/[)"'】。]+$/, '');return t.trim();}

async function extractClient(){
  let raw=document.getElementById('url').value;
  if(!raw){alert('วางลิงก์ก่อน');return;}
  let slink=extractUrl(raw);
  document.getElementById('status').innerHTML='กำลังแกะด้วยเน็ตไทย... '+slink;
  try{
    // Step 1: fetch slink via cors proxy
    let proxy1 = "https://api.allorigins.win/get?url="+encodeURIComponent(slink);
    let r1 = await fetch(proxy1);
    let j1 = await r1.json();
    let html1 = j1.contents;
    // find sid url
    let m = html1.match(/https:\\/\\/www\\.bigo\\.tv\\/sid\\/[^\\s"'<>]+/);
    let sidUrl = m ? m[0] : "";
    if(!sidUrl){
      // try second proxy
      let proxy1b = "https://corsproxy.io/?"+encodeURIComponent(slink);
      let r1b = await fetch(proxy1b);
      let html1b = await r1b.text();
      let m2 = html1b.match(/https:\\/\\/www\\.bigo\\.tv\\/sid\\/[^\\s"'<>]+/);
      sidUrl = m2 ? m2[0] : "";
    }
    if(!sidUrl){ document.getElementById('status').innerHTML='หา sid ไม่เจอ ลองวางลิงก์ bigo.tv/sid/ โดยตรง'; return; }
    sidUrl = sidUrl.replace(/&amp;/g,'&');
    document.getElementById('status').innerHTML='เจอ SID: '+sidUrl.slice(0,80)+'...<br>กำลังโหลดหน้าไลฟ์...';
    
    // Step 2: fetch sid page
    let proxy2 = "https://api.allorigins.win/get?url="+encodeURIComponent(sidUrl);
    let r2 = await fetch(proxy2);
    let j2 = await r2.json();
    let html2 = j2.contents.replace(/\\\\\\//g,'/').replace(/\\\\u002F/g,'/');
    
    // Find m3u8
    let m3us = html2.match(/https?:\\/\\/[^\\s"'<>]+\\.m3u8[^\\s"'<>]*/g);
    if(!m3us || m3us.length==0){
      // try unescaped search
      let m3us2 = html2.match(/https?:[^\\s"'<>]*m3u8[^\\s"'<>]*/g);
      m3us = m3us2;
    }
    if(m3us && m3us.length>0){
      // filter best
      let unique=[...new Set(m3us)];
      foundHls=unique[0].replace(/\\\\/g,'').replace(/\\u002F/g,'/');
      // clean
      foundHls=foundHls.split('"')[0].split("'")[0].split('<')[0];
      document.getElementById('hls').value=foundHls;
      document.getElementById('status').innerHTML='เจอ HLS แล้ว! '+unique.length+' ลิงก์<br>'+foundHls.slice(0,100)+'<br>กำลังลองเล่น preview...';
      // try play
      let video=document.getElementById('video');
      if(Hls.isSupported()){
        let hlsjs=new Hls();
        hlsjs.loadSource(foundHls);
        hlsjs.attachMedia(video);
        hlsjs.on(Hls.Events.MANIFEST_PARSED,()=>video.play());
      } else if(video.canPlayType('application/vnd.apple.mpegurl')){
        video.src=foundHls;
        video.play();
      }
    } else {
      document.getElementById('status').innerHTML='ไม่เจอ m3u8 ในหน้า HTML แบบตรงๆ<br>HTML preview:<br><pre>'+html2.slice(0,2000)+'</pre>';
      // try to find via API that client can call (client IP Thai will get JSON)
      let siteIdMatch = sidUrl.match(/\\/sid\\/(\\d+)_/);
      let siteId = siteIdMatch ? siteIdMatch[1] : "";
      if(siteId){
        document.getElementById('status').innerHTML+='<br>ลองเรียก API ด้วยเน็ตไทย siteId='+siteId;
        let apiUrl = "https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId="+siteId;
        let proxyApi = "https://api.allorigins.win/get?url="+encodeURIComponent(apiUrl);
        let rApi = await fetch(proxyApi);
        let jApi = await rApi.json();
        let body = jApi.contents;
        document.getElementById('status').innerHTML+='<br>API response: '+body.slice(0,2000);
        let mApi = body.match(/https?:\\/\\/[^\\s"'<>]+\\.m3u8[^\\s"'<>]*/);
        if(mApi){
          foundHls=mApi[0];
          document.getElementById('hls').value=foundHls;
          document.getElementById('status').innerHTML+='<br>เจอจาก API ไทย: '+foundHls;
        }
      }
    }
  }catch(e){
    document.getElementById('status').innerHTML='Error แกะ: '+e+'<br>ลองวางลิงก์ https://www.bigo.tv/sid/... โดยตรงแทน slink';
  }
}

async function startRecord(){
  let hls=document.getElementById('hls').value.trim();
  if(!hls){alert('ยังไม่มี HLS กรุณากด ขั้นตอน 1 ก่อน');return;}
  let q=document.getElementById('q').value;
  document.getElementById('status').innerHTML='ส่ง HLS ให้ Server บันทึก...';
  let r=await fetch('/api/start_direct',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hls,quality:q})});
  let j=await r.json();
  document.getElementById('status').innerHTML='OK ID '+j.id+' เริ่มบันทึกแล้ว HLS:'+hls.slice(0,60);
  load();
}
async function load(){let r=await fetch('/api/list');let j=await r.json();let h='';j.forEach(it=>{let cls=it.status=='done'?'done':(it.status=='error'?'error':'');h+='<div class="card '+cls+'"><b>'+(it.hls||it.resolved||'').slice(0,100)+'</b> <small style=float:right>'+it.status+'</small><br><small>'+it.time+' '+it.quality+'</small><pre>'+(it.log||'')+'</pre></div>';});document.getElementById('list').innerHTML=h;}
setInterval(load,3000);load();
</script></body></html>
"""
HEADERS={"User-Agent":"Mozilla/5.0","Referer":"https://www.bigo.tv/"}

@app.route("/")
def home(): return HTML_PAGE

@app.route("/api/start_direct", methods=["POST"])
def api_start_direct():
 data=request.json
 hls=data.get("hls","").strip()
 quality=data.get("quality","best")
 job_id=uuid.uuid4().hex[:8]
 out=os.path.join(RECORD_DIR, f"{job_id}.mp4")
 jobs[job_id]={"id":job_id,"hls":hls,"resolved":hls,"siteid":"direct","quality":quality,"status":"recording","log":f"Direct HLS: {hls[:300]}\n","time":datetime.now().strftime("%H:%M:%S %d/%m"),"file":out}
 def run():
  try:
   cmd=["ffmpeg","-y","-user_agent","Mozilla/5.0","-referer","https://www.bigo.tv/","-i",hls,"-c","copy",out]
   proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
   for line in proc.stdout:
    jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-10000:]
   proc.wait()
   jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
  except Exception as e:
   jobs[job_id]["log"]+=str(e)
   jobs[job_id]["status"]="error"
 threading.Thread(target=run, daemon=True).start()
 return jsonify({"id":job_id,"hls":hls})

@app.route("/api/list")
def api_list(): return jsonify(list(jobs.values())[::-1])

@app.route("/api/start", methods=["POST"])
def api_start_old():
 data=request.json
 return jsonify({"id":"use_direct","resolved":"","siteid":""})
if __name__=="__main__": app.run(host="0.0.0.0", port=5000)
