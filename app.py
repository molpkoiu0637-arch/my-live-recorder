import os, re, subprocess, threading, uuid, time
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
RECORD_DIR = "/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs = {}

HTML_PAGE = """
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>REAL CLOUD V4 FIX</title>
<style>body{background:#111;color:#fff;font-family:system-ui;padding:20px}input,select,button{width:100%;padding:14px;margin:8px 0;border-radius:12px;border:none;font-size:16px}button{background:linear-gradient(90deg,#a855f7,#ec4899);color:#fff;font-weight:bold}.card{background:#1e1e1e;border-radius:16px;padding:14px;margin:12px 0;border-left:4px solid #22c55e}.card.error{border-color:#ef4444}pre{background:#000;padding:10px;border-radius:8px;overflow:auto;white-space:pre-wrap;font-size:12px;max-height:200px}</style>
</head><body>
<h2>REAL CLOUD <span style="background:#22c55e;color:#000;padding:4px 10px;border-radius:20px;font-size:14px">V4 SSL FIXED</span></h2>
<p style="color:#aaa">วางลิงก์จีนยาวๆได้ ระบบตัดให้เอง - YouTube แก้ SSL แล้ว</p>
<input id="url" placeholder="วางลิงก์ที่นี่">
<select id="q"><option>best</option><option>1080p</option><option>720p</option><option>480p SD</option></select>
<button onclick="start()">เริ่มบันทึกทันที</button>
<div id="status"></div><div id="list"></div>
<script>
function extractUrl(t){
  let m = t.match(/https?:\/\/[^\s]+/);
  if(m) return m[0].replace(/[)\"'】。]+$/, '');
  m = t.match(/v\.douyin\.com\/[^\s]+/);
  if(m) return 'https://'+m[0];
  return t.trim();
}
async function start(){
  let raw=document.getElementById('url').value;
  if(!raw) return alert('วางลิงก์ก่อน');
  let url=extractUrl(raw);
  document.getElementById('url').value=url;
  let q=document.getElementById('q').value;
  let r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,quality:q})});
  let j=await r.json();
  document.getElementById('status').innerHTML='<div style=color:#22c55e>OK ID '+j.id+'</div>';
  load();
}
async function load(){
  let r=await fetch('/api/list');let j=await r.json();
  let h='';
  j.forEach(it=>{
    h+=`<div class="card ${it.status=='error'?'error':''}"><b>${it.url.slice(0,60)}</b> <small style=float:right>${it.status}</small><br><small>${it.time} - ${it.quality}</small><pre>${it.log||''}</pre></div>`;
  });
  document.getElementById('list').innerHTML=h;
}
setInterval(load,3000);load();
</script></body></html>
"""

def clean_url(raw):
    if not raw: return raw
    m = re.search(r'https?://[^\s\u4e00-\u9fff]+', raw)
    if m:
        url = m.group(0)
        url = re.sub(r'[\]\)\"\'\]】。]+$', '', url)
        return url
    m = re.search(r'v\.douyin\.com/[^\s]+', raw)
    if m:
        return 'https://' + m.group(0)
    return raw.strip()

@app.route("/")
def home():
    return HTML_PAGE

@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.json
    raw_url = data.get("url","").strip()
    url = clean_url(raw_url)
    quality = data.get("quality","best")
    job_id = uuid.uuid4().hex[:12]
    out = os.path.join(RECORD_DIR, f"{job_id}.mp4")
    jobs[job_id] = {"id":job_id,"url":url,"raw":raw_url,"quality":quality,"status":"starting","log":"","time":datetime.now().strftime("%H:%M:%S %d/%m"),"file":out}
    def run():
        try:
            jobs[job_id]["status"]="recording"
            q_map = {"best":"best","1080p":"best[height<=1080]","720p":"best[height<=720]","480p SD":"best[height<=480]"}
            fmt = q_map.get(quality, "best")
            # Important: --no-check-certificate fixes YouTube SSL
            cmd = ["yt-dlp","--no-check-certificate","--no-playlist","-f",fmt,"-o",out,"--merge-output-format","mp4",url]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                jobs[job_id]["log"] = (jobs[job_id]["log"] + line)[-4000:]
            proc.wait()
            jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
        except Exception as e:
            jobs[job_id]["log"]+=str(e)
            jobs[job_id]["status"]="error"
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"id":job_id,"url":url})

@app.route("/api/list")
def api_list():
    return jsonify(list(jobs.values())[::-1])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
