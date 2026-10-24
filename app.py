import os, re, subprocess, threading, uuid, time, requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
RECORD_DIR = "/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs = {}

HTML_PAGE = """
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>BIGO V10</title>
<style>body{background:#111;color:#fff;font-family:system-ui;padding:20px}input,select,button{width:100%;padding:14px;margin:8px 0;border-radius:12px;border:none;font-size:16px}button{background:linear-gradient(90deg,#22c55e,#16a34a);color:#fff;font-weight:bold}.card{background:#1e1e1e;border-radius:16px;padding:14px;margin:12px 0;border-left:4px solid #22c55e}.card.error{border-color:#ef4444}pre{background:#000;padding:10px;border-radius:8px;overflow:auto;white-space:pre-wrap;font-size:12px;max-height:250px}.ok{color:#22c55e;font-weight:bold}</style>
</head><body>
<h2>BIGO V10 <span style="background:#22c55e;color:#000;padding:4px 10px;border-radius:20px;font-size:14px">BYPASS IP BLOCK</span></h2>
<p style="color:#aaa">แก้บั๊ก not live หลอก - ดึงตรงจาก Bigo API</p>
<input id="url" placeholder="วางลิงก์ Bigo ตอนไลฟ์อยู่">
<select id="q"><option>best</option><option>1080p</option><option>720p</option><option>480p SD</option></select>
<button onclick="start()">เริ่มบันทึกทันที</button>
<div id="status" style="padding:10px" class="ok"></div><div id="list"></div>
<script>
function extractUrl(t){let m=t.match(/https?:\/\/[^\s]+/);if(m) return m[0].replace(/[)"'】。]+$/, '');return t.trim();}
async function start(){
  let raw=document.getElementById('url').value;if(!raw){alert('วางลิงก์ก่อน');return;}
  let url=extractUrl(raw);document.getElementById('status').innerHTML='กำลังเริ่ม... '+url;
  let q=document.getElementById('q').value;
  try{let r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,quality:q})});let j=await r.json();document.getElementById('status').innerHTML='OK ID '+j.id+'<br>SiteID:'+j.siteid+'<br>HLS:'+(j.hls?'เจอแล้ว':'กำลังหา');}catch(e){document.getElementById('status').innerHTML='Error: '+e;}
  load();
}
async function load(){let r=await fetch('/api/list');let j=await r.json();let h='';j.forEach(it=>{h+='<div class="card '+(it.status=='error'?'error':'')+'"><b>'+it.url.slice(0,90)+'</b> <small style=float:right>'+it.status+'</small><br><small>'+it.time+' - '+it.quality+' - Site:'+it.siteid+'</small><pre>'+(it.log||'')+'</pre></div>';});document.getElementById('list').innerHTML=h;}
setInterval(load,3000);load();
</script></body></html>
"""

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Referer": "https://www.bigo.tv/",
    "Origin": "https://www.bigo.tv"
}

def resolve_slink(url):
    try:
        if "slink.bigovideo.tv" in url or "bigo.tv" in url and len(url)<60:
            r = requests.get(url, allow_redirects=True, timeout=15, headers=HEADERS)
            return r.url
    except Exception as e:
        pass
    return url

def clean_url(raw):
    m = re.search(r"https?://[^\s\u4e00-\u9fa5]+", raw)
    url = m.group(0) if m else raw
    url = url.strip().strip(')"\'】。')
    url = resolve_slink(url)
    url = url.split("?")[0].split("&")[0].rstrip("/")
    return url

def get_bigo_hls(site_id):
    # try multiple APIs
    urls = [
        f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}",
        f"https://ta.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}",
        f"https://www.bigo.tv/official_website/studion/getinfo?siteId={site_id}",
        f"https://www.bigo.tv/api/v2/bigo/getLiveStreamInfo?siteId={site_id}",
    ]
    logs = ""
    for api_url in urls:
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=10)
            logs += f"ลอง API: {api_url} -> {r.status_code}\n"
            if r.status_code==200:
                try:
                    j = r.json()
                    # find hls anywhere
                    txt = r.text
                    # look for .m3u8
                    m = re.search(r"https?://[^\s\"']+\.m3u8[^\s\"']*", txt)
                    if m:
                        logs += f"เจอ HLS: {m.group(0)[:100]}\n"
                        return m.group(0), logs
                    # look in json structure
                    if "data" in j:
                        # try common paths
                        for k in ["hls","alive_hls","live_url","video_url","hls_url","play_url","url"]:
                            if k in str(j):
                                # deep search
                                def find(obj):
                                    if isinstance(obj,str) and ".m3u8" in obj:
                                        return obj
                                    if isinstance(obj,dict):
                                        for v in obj.values():
                                            res=find(v)
                                            if res: return res
                                    if isinstance(obj,list):
                                        for v in obj:
                                            res=find(v)
                                            if res: return res
                                    return None
                                found=find(j)
                                if found:
                                    return found, logs + f"เจอใน json {k}\n"
                    logs += f"Response: {txt[:500]}\n"
                except Exception as e:
                    logs += f"parse error {e} body {r.text[:300]}\n"
        except Exception as e:
            logs += f"API {api_url} error {e}\n"
    return None, logs

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

    # extract siteId
    m = re.search(r"/sid/(\d+)_", url)
    if not m:
        m = re.search(r"bigo\.tv/(\d+)", url)
    site_id = m.group(1) if m else "unknown"
    out = os.path.join(RECORD_DIR, f"{job_id}.mp4")
    jobs[job_id] = {"id":job_id,"url":url,"raw":raw_url,"siteid":site_id,"quality":quality,"status":"starting","log":"","time":datetime.now().strftime("%H:%M:%S %d/%m"),"file":out}

    def run():
        try:
            jobs[job_id]["status"]="recording"
            log_acc = f"Cleaned URL: {url}\nSiteID: {site_id}\n"
            
            # For Bigo, bypass yt-dlp check
            if "bigo.tv" in url and site_id!="unknown":
                hls, api_log = get_bigo_hls(site_id)
                log_acc += api_log
                if hls:
                    jobs[job_id]["log"]=log_acc + f"\nเจอ HLS จริง กำลังบันทึก...\n{hls[:150]}\n"
                    # record directly with ffmpeg from m3u8
                    cmd = ["ffmpeg","-y","-user_agent", HEADERS["User-Agent"], "-referer", "https://www.bigo.tv/", "-i", hls, "-c","copy", out]
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in proc.stdout:
                        jobs[job_id]["log"] = (jobs[job_id]["log"] + line)[-5000:]
                    proc.wait()
                    jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
                    return
                else:
                    log_acc += "\nไม่เจอ HLS จาก API โดยตรง จะลอง yt-dlp แบบบังคับ (อาจขึ้น not live หลอก ถ้าโดนบล็อก IP)\n"

            # Fallback yt-dlp for other platforms
            q_map = {"best":"best","1080p":"best[height<=1080]","720p":"best[height<=720]","480p SD":"best[height<=480]"}
            fmt = q_map.get(quality, "best")
            cmd = ["yt-dlp","--no-check-certificate","--no-playlist","-f",fmt,"-o",out,"--merge-output-format","mp4",url]
            log_acc += f"CMD: {' '.join(cmd)}\n"
            jobs[job_id]["log"]=log_acc
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                jobs[job_id]["log"] = (jobs[job_id]["log"] + line)[-5000:]
            proc.wait()
            jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
        except Exception as e:
            jobs[job_id]["log"]+=str(e)
            jobs[job_id]["status"]="error"

    threading.Thread(target=run, daemon=True).start()
    hls_check, _ = ("", "")
    return jsonify({"id":job_id,"url":url,"siteid":site_id,"hls":False,"raw":raw_url})

@app.route("/api/list")
def api_list():
    return jsonify(list(jobs.values())[::-1])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
