
import os, re, subprocess, threading, uuid, time, requests, json
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
RECORD_DIR = "/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs = {}

HTML_PAGE = """
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>REAL CLOUD V9</title>
<style>body{background:#111;color:#fff;font-family:system-ui;padding:20px}input,select,button{width:100%;padding:14px;margin:8px 0;border-radius:12px;border:none;font-size:16px}button{background:linear-gradient(90deg,#a855f7,#ec4899);color:#fff;font-weight:bold}.card{background:#1e1e1e;border-radius:16px;padding:14px;margin:12px 0;border-left:4px solid #22c55e}.card.error{border-color:#ef4444}pre{background:#000;padding:10px;border-radius:8px;overflow:auto;white-space:pre-wrap;font-size:12px;max-height:300px}.badge{background:#22c55e;color:#000;padding:4px 10px;border-radius:20px;font-size:13px}</style>
</head><body>
<h2>REAL CLOUD <span class=badge>V9 BIGO DIRECT</span></h2>
<p style="color:#aaa">รองรับ slink + sid แบบใหม่ บายพาสบล็อก IP</p>
<input id="url" placeholder="วางลิงก์ Bigo / YouTube / TikTok">
<select id="q"><option>best</option><option>1080p</option><option>720p</option><option>480p SD</option></select>
<button onclick="start()">เริ่มบันทึกทันที</button>
<div id="status" style="padding:10px;color:#22c55e;font-weight:bold"></div><div id="list"></div>
<script>
async function start(){
  let raw=document.getElementById('url').value;
  if(!raw){alert('วางลิงก์ก่อน');return;}
  let q=document.getElementById('q').value;
  document.getElementById('status').innerHTML='กำลังเริ่ม...';
  let r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:raw,quality:q})});
  let j=await r.json();
  document.getElementById('status').innerHTML='OK ID '+j.id+' URL:'+j.url.slice(0,60);
  load();
}
async function load(){
  let r=await fetch('/api/list');let j=await r.json();
  let h='';
  j.forEach(it=>{
    h+='<div class="card '+(it.status=='error'?'error':'')+'"><b>'+it.url.slice(0,80)+'</b> <small style=float:right>'+it.status+'</small><br><small>'+it.time+' • '+it.quality+' • ID:'+it.id+'</small><pre>'+(it.log||'').slice(-2000)+'</pre></div>';
  });
  document.getElementById('list').innerHTML=h;
}
setInterval(load,3000);load();
</script></body></html>
"""

def resolve_slink(url):
    url = url.strip()
    try:
        if "slink.bigovideo.tv" in url or "bigovideo" in url:
            headers = {"User-Agent":"Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"}
            # GET page because JS redirect
            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            text = resp.text
            # find bigo.tv url in text
            m = re.search(r"https://www\.bigo\.tv/[^\"'\s]+", text)
            if m:
                return m.group(0)
            m2 = re.search(r"bigo\.tv/sid/[\d_]+", text)
            if m2:
                return "https://www."+m2.group(0)
            # if final url is bigo.tv already
            if "bigo.tv" in resp.url:
                return resp.url
    except Exception as e:
        print("resolve error", e)
    return url

def extract_bigo_siteid(url):
    # from https://www.bigo.tv/sid/2894192156_1821679764_1792823052 or https://www.bigo.tv/2894192156
    m = re.search(r"/sid/(\d+)_\d+_\d+", url)
    if m:
        return m.group(1)
    m = re.search(r"bigo\.tv/(?:[a-z]{2}/)?(\d{5,})", url)
    if m:
        return m.group(1)
    return None

def get_bigo_hls(site_id):
    try:
        headers = {
            "User-Agent":"Mozilla/5.0",
            "Referer":"https://www.bigo.tv/",
            "Origin":"https://www.bigo.tv"
        }
        # try new API
        api_url = f"https://ta.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}"
        r = requests.get(api_url, headers=headers, timeout=10)
        data = r.json()
        # data structure: data.data.hls or liveUrl
        j = data.get("data") or data
        # search for hls
        for k in ["hls","liveUrl","videoUrl","src","flv","rtmp"]:
            if k in str(j):
                pass
        # brute find m3u8 url
        txt = json.dumps(data)
        m = re.search(r"https://[^\"]+\.m3u8[^\"]*", txt)
        if m:
            return m.group(0).replace("\\u002F","/").replace("\\","")
        # alternative endpoint
        api2 = f"https://www.bigo.tv/official_website/studio/getBigoRoomInfo?siteId={site_id}"
        r2 = requests.get(api2, headers=headers, timeout=10)
        m = re.search(r"https://[^\"]+\.m3u8[^\"]*", r2.text)
        if m:
            return m.group(0)
    except Exception as e:
        print("bigo api error", e)
    return None

def clean_url(raw):
    raw = raw.strip()
    m = re.search(r"https?://[^\s\u4e00-\u9fa5]+", raw)
    url = m.group(0) if m else raw
    url = url.strip().strip(')"\'】。')
    url = resolve_slink(url)
    url = url.split("?")[0].split("&")[0].rstrip("/")
    return url

@app.route("/")
def home():
    return HTML_PAGE

@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.json
    raw_url = data.get("url","").strip()
    url = clean_url(raw_url)
    quality = data.get("quality","best")
    job_id = uuid.uuid4().hex[:8]
    out = os.path.join(RECORD_DIR, f"{job_id}.mp4")
    jobs[job_id] = {"id":job_id,"url":url,"raw":raw_url,"quality":quality,"status":"starting","log":f"Cleaned URL: {url}\n","time":datetime.now().strftime("%H:%M:%S %d/%m"),"file":out}
    def run():
        try:
            jobs[job_id]["status"]="recording"
            # BIGO direct mode
            if "bigo.tv" in url:
                sid = extract_bigo_siteid(url)
                jobs[job_id]["log"]+=f"SiteID: {sid}\n"
                hls = get_bigo_hls(sid) if sid else None
                if hls:
                    jobs[job_id]["log"]+=f"Found HLS: {hls[:100]}...\n ใช้ ffmpeg อัดโดยตรง\n"
                    cmd = ["ffmpeg","-y","-i",hls,"-c","copy",out]
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in proc.stdout:
                        jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-5000:]
                    proc.wait()
                    jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
                    return
                else:
                    jobs[job_id]["log"]+="ไม่เจอ HLS จาก API ลอง yt-dlp ต่อ...\n"
            # fallback yt-dlp for all
            q_map = {"best":"best","1080p":"best[height<=1080]","720p":"best[height<=720]","480p SD":"best[height<=480]"}
            fmt = q_map.get(quality,"best")
            cmd = ["yt-dlp","--no-check-certificate","--no-playlist","-f",fmt,"-o",out,"--merge-output-format","mp4",url]
            jobs[job_id]["log"]+=f"CMD: {' '.join(cmd)}\n"
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-5000:]
            proc.wait()
            jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
        except Exception as e:
            jobs[job_id]["log"]+=f"\nException: {e}\n"
            jobs[job_id]["status"]="error"
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"id":job_id,"url":url,"raw":raw_url})

@app.route("/api/list")
def api_list():
    return jsonify(list(jobs.values())[::-1])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
