import os, re, subprocess, threading, uuid
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
jobs = {}

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>REAL CLOUD V5</title>
<style>
body{background:#111;color:#fff;font-family:sans-serif;padding:20px}
input,select,button{width:100%;padding:14px;margin:8px 0;border-radius:12px;border:none;font-size:16px}
button{background:linear-gradient(90deg,#a855f7,#ec4899);color:#fff;font-weight:bold}
.card{background:#1e1e1e;border-radius:12px;padding:12px;margin:10px 0;border-left:4px solid #22c55e}
.card.error{border-color:#ef4444}
pre{background:#000;padding:8px;border-radius:6px;font-size:11px;max-height:180px;overflow:auto;white-space:pre-wrap}
</style></head><body>
<h2>REAL CLOUD <span style="background:#22c55e;color:#000;padding:4px 10px;border-radius:20px;font-size:14px">V5 SSL OK</span></h2>
<p style="color:#aaa">วางลิงก์ยาวๆได้ ตัดให้อัตโนมัติ</p>
<input id="url" placeholder="วางลิงก์ YouTube / Douyin / Bigo">
<select id="q"><option>best</option><option>1080p</option><option>720p</option><option>480p SD</option></select>
<button onclick="start()">เริ่มบันทึก</button>
<div id="s"></div><div id="list"></div>
<script>
function extractUrl(t){
  var m = t.match(/https?:\/\/[^\s\u4e00-\u9fa5]+/);
  if(m) return m[0].replace(/[)\"'\]]+$/, "");
  m = t.match(/v\.douyin\.com\/[^\s]+/);
  if(m) return "https://"+m[0];
  return t.trim();
}
async function start(){
  var raw=document.getElementById("url").value;
  if(!raw) return alert("วางลิงก์ก่อน");
  var url=extractUrl(raw);
  document.getElementById("url").value=url;
  var q=document.getElementById("q").value;
  var r=await fetch("/api/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:url,quality:q})});
  var j=await r.json();
  document.getElementById("s").innerHTML="<div style=color:#22c55e>OK ID "+j.id+"</div>";
  load();
}
async function load(){
  var r=await fetch("/api/list");var j=await r.json();
  var h="";
  j.forEach(it=>{
    h+='<div class="card '+(it.status=="error"?"error":"")+'"><b>'+it.url.slice(0,60)+'</b> <small style=float:right>'+it.status+'</small><br><small>'+it.time+'</small><pre>'+(it.log||"")+'</pre></div>';
  });
  document.getElementById("list").innerHTML=h;
}
setInterval(load,3000);load();
</script></body></html>
"""

def clean_url(raw):
    m = re.search(r"https?://[^\s]+", raw)
    if m:
        return m.group(0).strip().strip(')"\'】')
    m = re.search(r"v\.douyin\.com/[^\s]+", raw)
    if m:
        return "https://" + m.group(0)
    return raw.strip()

@app.route("/")
def home():
    return HTML

@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json()
    raw_url = data.get("url","").strip()
    url = clean_url(raw_url)
    quality = data.get("quality","best")
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {"id":job_id,"url":url,"quality":quality,"status":"starting","log":"","time":datetime.now().strftime("%H:%M:%S")}
    def run():
        try:
            jobs[job_id]["status"]="recording"
            qmap={"best":"best","1080p":"best[height<=1080]","720p":"best[height<=720]","480p SD":"best[height<=480]"}
            fmt=qmap.get(quality,"best")
            out=f"/tmp/{job_id}.mp4"
            cmd=["yt-dlp","--no-check-certificate","--no-playlist","-f",fmt,"-o",out,url]
            proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            log=""
            for line in proc.stdout:
                log+=line
                jobs[job_id]["log"]=log[-3000:]
            proc.wait()
            jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
        except Exception as e:
            jobs[job_id]["log"]+=str(e)
            jobs[job_id]["status"]="error"
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"id":job_id})

@app.route("/api/list")
def api_list():
    return jsonify(list(jobs.values())[::-1])
