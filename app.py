import os, subprocess, threading, uuid
from flask import Flask, request, jsonify
from datetime import datetime
app=Flask(__name__)
RECORD_DIR="/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs={}
HTML_PAGE = """
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>BIGO V17 ULTRA SIMPLE</title>
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<style>body{background:#111;color:#fff;font-family:system-ui;padding:16px;line-height:1.6}input,button,textarea{width:100%;padding:14px;margin:8px 0;border-radius:12px;border:none;font-size:14px;box-sizing:border-box}button{background:#22c55e;color:#000;font-weight:bold}button.orange{background:#f59e0b}.card{background:#1e1e1e;border-radius:12px;padding:12px;margin:10px 0;border-left:4px solid #22c55e}.bookmark{background:#27272a;border:2px dashed #f59e0b;padding:14px;border-radius:12px;margin:12px 0}.ok{color:#22c55e;font-weight:bold}pre{background:#000;padding:10px;border-radius:8px;overflow:auto;white-space:pre-wrap;font-size:11px}video{width:100%;border-radius:12px;background:#000}</style>
</head><body>
<h2>BIGO V17 <span style="background:#22c55e;color:#000;padding:4px 10px;border-radius:12px;font-size:12px">ULTRA SIMPLE</span></h2>

<div class="bookmark">
<b>📌 วิธีได้ HLS 100% (ทำครั้งเดียว):</b><br>
1. เปิดไลฟ์ Bigo ที่จะอัดใน Chrome (เปิด https://www.bigo.tv/sid/... )<br>
2. ก็อปโค้ดนี้ไปสร้าง Bookmark:<br>
<textarea rows="3" id="bm" style="font-size:11px">javascript:(()=>{let h=document.documentElement.innerHTML;let m=h.match(/https:\\/\\/[^\\s"'<>]+\\.m3u8[^\\s"'<>]*/g);if(!m){m=(h.match(/https:\\\\\\/\\\\/[^\\\\]+m3u8/g)||[]);}let u=[...new Set(m||[])];if(u.length){let s=u.join("\\n");prompt("ก็อป HLS บรรทัดแรกไปวางใน V17:\\n\\n"+s,u[0]);}else{alert("ไม่เจอ HLS ลองรีเฟรชหน้าไลฟ์แล้วกดใหม่");}})();</textarea>
<button class="orange" onclick="copyBm()">ก็อปโค้ด Bookmark</button><br>
3. เปิดหน้าไลฟ์ Bigo แล้วกด Bookmark ที่สร้าง → มันจะเด้ง HLS มาให้ก็อป<br>
4. เอา HLS มาวางช่องล่างแล้วกดบันทึก
</div>

<textarea id="hls" rows="3" placeholder="วาง HLS ที่ได้จาก Bookmark ตรงนี้ เช่น https://.../index.m3u8"></textarea>
<video id="video" controls muted playsinline></video>
<select id="q"><option>best</option><option>720p</option><option>480p SD</option></select>
<button onclick="preview()">Preview วิดีโอ (เช็คว่า HLS ถูก)</button>
<button onclick="startRecord()" style="background:#22c55e">ส่ง HLS ให้ Server บันทึกเลย</button>
<div id="status" class="ok"></div>
<div id="list"></div>

<script>
function copyBm(){let e=document.getElementById('bm');e.select();document.execCommand('copy');alert('ก็อปแล้ว ไปสร้าง Bookmark วางได้เลย');}
function preview(){
  let hls=document.getElementById('hls').value.trim();
  if(!hls){alert('วาง HLS ก่อน');return;}
  let video=document.getElementById('video');
  document.getElementById('status').innerHTML='กำลัง preview: '+hls.slice(0,80);
  if(Hls.isSupported()){
    let hlsjs=new Hls();
    hlsjs.loadSource(hls);
    hlsjs.attachMedia(video);
    hlsjs.on(Hls.Events.MANIFEST_PARSED,()=>{video.play().catch(()=>{}); document.getElementById('status').innerHTML='Preview OK กำลังเล่น...';});
    hlsjs.on(Hls.Events.ERROR,(e,d)=>{document.getElementById('status').innerHTML='HLS Error: '+JSON.stringify(d);});
  } else if(video.canPlayType('application/vnd.apple.mpegurl')){
    video.src=hls; video.play().catch(()=>{});
  }
}
async function startRecord(){
  let hls=document.getElementById('hls').value.trim();
  if(!hls){alert('วาง HLS ก่อน');return;}
  let q=document.getElementById('q').value;
  document.getElementById('status').innerHTML='ส่งให้ Server บันทึก...';
  let r=await fetch('/api/start_direct',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hls,quality:q})});
  let j=await r.json();
  document.getElementById('status').innerHTML='OK ID '+j.id+' เริ่มบันทึกแล้ว ดู Log ข้างล่าง';
  load();
}
async function load(){let r=await fetch('/api/list');let j=await r.json();let h='';j.forEach(it=>{let cls=it.status=='done'?'done':(it.status=='error'?'error':'');h+='<div class="card '+cls+'"><b>'+(it.hls||'').slice(0,120)+'</b> <small style=float:right>'+it.status+'</small><br><small>'+it.time+'</small><pre>'+(it.log||'').slice(-3000)+'</pre></div>';});document.getElementById('list').innerHTML=h;}
setInterval(load,3000);load();
</script></body></html>
"""
@app.route("/")
def home(): return HTML_PAGE
@app.route("/api/start_direct", methods=["POST"])
def api_start_direct():
 data=request.json
 hls=data.get("hls","").strip().split()[0]
 quality=data.get("quality","best")
 job_id=__import__("uuid").uuid4().hex[:8]
 out=os.path.join(RECORD_DIR, f"{job_id}.mp4")
 jobs[job_id]={"id":job_id,"hls":hls,"quality":quality,"status":"recording","log":f"Direct HLS: {hls[:800]}\n","time":datetime.now().strftime("%H:%M:%S %d/%m"),"file":out}
 def run():
  try:
   cmd=["ffmpeg","-y","-user_agent","Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15","-referer","https://www.bigo.tv/","-i",hls,"-c","copy","-t","7200",out]
   proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
   for line in proc.stdout:
    jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-15000:]
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
