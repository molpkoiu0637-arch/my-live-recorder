import os, re, subprocess, threading, uuid
from flask import Flask, request, jsonify
from datetime import datetime
app=Flask(__name__)
RECORD_DIR="/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs={}
HTML_PAGE = """
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>BIGO V16 FINAL</title>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<style>body{background:#111;color:#fff;font-family:system-ui;padding:16px}input,select,button,textarea{width:100%;padding:13px;margin:7px 0;border-radius:12px;border:none;font-size:14px;box-sizing:border-box}button{background:#22c55e;color:#000;font-weight:bold}button.orange{background:#f59e0b}.card{background:#1e1e1e;border-radius:12px;padding:12px;margin:10px 0;border-left:4px solid #22c55e}pre{background:#000;padding:8px;border-radius:8px;overflow:auto;white-space:pre-wrap;font-size:10px;max-height:400px}.ok{color:#22c55e}video{width:100%;border-radius:12px;background:#000}</style>
</head><body>
<h2>BIGO V16 <span style="background:#22c55e;color:#000;padding:4px 10px;border-radius:12px;font-size:12px">FINAL</span></h2>
<p style="color:#aaa;font-size:12px">วิธีที่ได้ 100%: เปิด slink ใน Chrome -> ก็อปลิงก์ bigo.tv/sid/... ยาวๆ มาวาง</p>
<input id="url" placeholder="วาง https://www.bigo.tv/sid/2898456499_... ยาวๆ">
<button class="orange" onclick="extractClient()">แกะ HLS ด้วยเน็ตไทย</button>
<textarea id="hls" rows="3" placeholder="HLS จะขึ้นตรงนี้"></textarea>
<video id="video" controls muted playsinline></video>
<select id="q"><option>best</option><option>720p</option><option>480p SD</option></select>
<button onclick="startRecord()">ส่ง HLS ให้ Server บันทึก</button>
<div id="status" class="ok"></div>
<div id="list"></div>
<script>
async function fetchWithProxy(url){
  let proxies = [
    "https://api.codetabs.com/v1/proxy?quest="+encodeURIComponent(url),
    "https://corsproxy.io/?"+encodeURIComponent(url),
    "https://api.allorigins.win/raw?url="+encodeURIComponent(url),
    "https://thingproxy.freeboard.name/fetch/"+url
  ];
  for(let p of proxies){
    try{
      let r = await fetch(p);
      if(!r.ok) continue;
      let txt = await r.text();
      if(txt && txt.length>1000 && (txt.includes("m3u8") || txt.includes("bigo") || txt.includes("<html"))){
        return txt;
      }
    }catch(e){}
  }
  throw "proxy fail";
}

async function extractClient(){
  let raw=document.getElementById('url').value.trim();
  if(!raw){alert('วางลิงก์ sid ยาวๆ');return;}
  // clean
  let sidUrl = raw.match(/https?:\\/\\/[^\\s]+/) ? raw.match(/https?:\\/\\/[^\\s]+/)[0].replace(/[)"']+$/,'') : raw;
  sidUrl = sidUrl.replace(/&amp;/g,'&');
  document.getElementById('status').innerHTML='กำลังแกะด้วยเน็ตไทย...<br>'+sidUrl.slice(0,80);
  try{
    let html = await fetchWithProxy(sidUrl);
    html = html.replace(/\\\\\\//g,'/').replace(/\\\\u002F/g,'/').replace(/\\\\u002f/g,'/');
    // find m3u8
    let m3us = html.match(/https?:\\/\\/[^\\s"'<>]+\\.m3u8[^\\s"'<>]*/g);
    if(!m3us){
      // try encoded
      let dec = html.replace(/\\u002F/g,'/').replace(/\\\\/g,'');
      m3us = dec.match(/https?:\\/\\/[^\\s"'<>]+\\.m3u8[^\\s"'<>]*/g);
    }
    if(m3us && m3us.length>0){
      let uniq=[...new Set(m3us)];
      // pick best (usually contains aliyun or bigo)
      let best = uniq.find(u=>u.includes("m3u8")) || uniq[0];
      // choose highest quality if multiple
      for(let u of uniq){ if(u.includes("hd") || u.includes("1080")) best=u; }
      best = best.split('"')[0].split("'")[0].split('\\')[0].split('<')[0];
      document.getElementById('hls').value=best;
      document.getElementById('status').innerHTML='เจอ HLS แล้ว! '+uniq.length+' ลิงก์<br>'+best.slice(0,120)+'<br>กำลัง preview...';
      let video=document.getElementById('video');
      try{
        if(Hls.isSupported()){
          let hlsjs=new Hls();
          hlsjs.loadSource(best);
          hlsjs.attachMedia(video);
          hlsjs.on(Hls.Events.MANIFEST_PARSED,()=>video.play().catch(()=>{}));
        } else if(video.canPlayType('application/vnd.apple.mpegurl')){
          video.src=best; video.play().catch(()=>{});
        }
      }catch(e){}
    } else {
      document.getElementById('status').innerHTML='ไม่เจอ m3u8 ในหน้า ลองเลื่อนดู HTML 2000 ตัวแรก:<br><pre>'+html.slice(0,3000)+'</pre>';
    }
  }catch(e){
    document.getElementById('status').innerHTML='Error: '+e+'<br>แนะนำ: เปิดลิงก์ sid ในมือถือแล้วกด View Source หรือลองเปลี่ยนเน็ต';
  }
}

async function startRecord(){
  let hls=document.getElementById('hls').value.trim();
  if(!hls){alert('ยังไม่มี HLS');return;}
  let q=document.getElementById('q').value;
  document.getElementById('status').innerHTML='ส่ง HLS ให้ Server...';
  let r=await fetch('/api/start_direct',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hls,quality:q})});
  let j=await r.json();
  document.getElementById('status').innerHTML='OK ID '+j.id+' เริ่มบันทึกแล้ว!';
  load();
}
async function load(){let r=await fetch('/api/list');let j=await r.json();let h='';j.forEach(it=>{let cls=it.status=='done'?'done':(it.status=='error'?'error':'');h+='<div class="card '+cls+'"><b>'+(it.hls||'').slice(0,100)+'</b> <small style=float:right>'+it.status+'</small><br><small>'+it.time+'</small><pre>'+(it.log||'').slice(0,2000)+'</pre></div>';});document.getElementById('list').innerHTML=h;}
setInterval(load,3000);load();
</script></body></html>
"""

@app.route("/")
def home(): return HTML_PAGE
@app.route("/api/start_direct", methods=["POST"])
def api_start_direct():
 data=request.json
 hls=data.get("hls","").strip()
 quality=data.get("quality","best")
 job_id=__import__("uuid").uuid4().hex[:8]
 out=os.path.join(RECORD_DIR, f"{job_id}.mp4")
 jobs[job_id]={"id":job_id,"hls":hls,"resolved":hls,"siteid":"direct","quality":quality,"status":"recording","log":f"Direct HLS: {hls[:500]}\n","time":datetime.now().strftime("%H:%M:%S %d/%m"),"file":out}
 def run():
  try:
   cmd=["ffmpeg","-y","-user_agent","Mozilla/5.0","-referer","https://www.bigo.tv/","-i",hls,"-c","copy",out]
   proc=__import__("subprocess").Popen(cmd, stdout=__import__("subprocess").PIPE, stderr=__import__("subprocess").STDOUT, text=True)
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
if __name__=="__main__": app.run(host="0.0.0.0", port=5000)
