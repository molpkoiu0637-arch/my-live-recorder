import os, re, subprocess, threading, uuid, time, requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
RECORD_DIR = "/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs = {}

HTML_PAGE = """
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>BIGO V11 SLINK FIX</title>
<style>body{background:#111;color:#fff;font-family:system-ui;padding:20px}input,select,button{width:100%;padding:14px;margin:8px 0;border-radius:12px;border:none;font-size:16px}button{background:linear-gradient(90deg,#22c55e,#16a34a);color:#fff;font-weight:bold}.card{background:#1e1e1e;border-radius:16px;padding:14px;margin:12px 0;border-left:4px solid #22c55e}.card.error{border-color:#ef4444}pre{background:#000;padding:10px;border-radius:8px;overflow:auto;white-space:pre-wrap;font-size:12px;max-height:300px}.ok{color:#22c55e;font-weight:bold}</style>
</head><body>
<h2>BIGO V11 <span style="background:#22c55e;color:#000;padding:4px 10px;border-radius:20px;font-size:14px">SLINK FIX</span></h2>
<p style="color:#aaa">แก้ slink.bigovideo.tv โดยเฉพาะ - แกะลิงก์สดได้</p>
<input id="url" placeholder="วาง slink.bigovideo.tv หรือ bigo.tv/sid/...">
<select id="q"><option>best</option><option>1080p</option><option>720p</option><option>480p SD</option></select>
<button onclick="start()">เริ่มบันทึกทันที</button>
<div id="status" class="ok"></div><div id="list"></div>
<script>
function extractUrl(t){let m=t.match(/https?:\/\/[^\s]+/);if(m) return m[0].replace(/[)"'】。]+$/, '');return t.trim();}
async function start(){
  let raw=document.getElementById('url').value;if(!raw){alert('วางลิงก์ก่อน');return;}
  let url=extractUrl(raw);document.getElementById('status').innerHTML='กำลังแกะลิงก์... '+url;
  let q=document.getElementById('q').value;
  let r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,quality:q})});let j=await r.json();
  document.getElementById('status').innerHTML='OK ID '+j.id+'<br>Resolved:'+j.resolved+'<br>SiteID:'+j.siteid;
  load();
}
async function load(){let r=await fetch('/api/list');let j=await r.json();let h='';j.forEach(it=>{h+='<div class="card '+(it.status=='error'?'error':'')+'"><b>'+it.resolved.slice(0,100)+'</b> <small style=float:right>'+it.status+'</small><br><small>'+it.time+' - '+it.quality+' - Site:'+it.siteid+'</small><pre>'+(it.log||'')+'</pre></div>';});document.getElementById('list').innerHTML=h;}
setInterval(load,3000);load();
</script></body></html>
"""

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Referer": "https://www.bigo.tv/",
    "Origin": "https://www.bigo.tv",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,th;q=0.8"
}

def resolve_slink(url):
    log = ""
    if "slink.bigovideo.tv" not in url:
        return url, log
    try:
        # Try with session to keep cookies
        s = requests.Session()
        r = s.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        log += f"slink GET {url} -> {r.status_code} final:{r.url}\n"
        # If final url is bigo.tv, return it
        if "bigo.tv" in r.url and "slink" not in r.url:
            return r.url, log
        # Parse HTML for bigo link
        text = r.text
        # Look for window.location or href containing bigo.tv/sid
        patterns = [
            r'https://www\.bigo\.tv/sid/[^\s"\'<>]+',
            r'https://www\.bigo\.tv/[^\s"\'<>]+/sid/[^\s"\'<>]+',
            r'https://bigo\.tv/sid/[^\s"\'<>]+',
            r'"canonical"\s+href="([^"]+bigo\.tv[^"]+)"',
            r'window\.location\s*=\s*["\']([^"\']+bigo[^"\']+)["\']',
            r'location\.href\s*=\s*["\']([^"\']+bigo[^"\']+)["\']',
            r'URL=([^"\'>]+bigo\.tv[^"\'<>]+)',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                found = m.group(1) if m.lastindex else m.group(0)
                log += f"เจอใน HTML pattern {pat}: {found}\n"
                return found, log
        # Look for siteId in page
        m = re.search(r'siteId["\']?\s*[:=]\s*["\']?(\d+)', text)
        if m:
            sid = m.group(1)
            log += f"เจอ siteId {sid} ในหน้า slink\n"
            # construct fake sid url to trigger API
            return f"https://www.bigo.tv/sid/{sid}_0_0", log
        log += f"HTML preview: {text[:800]}\n"
    except Exception as e:
        log += f"slink resolve error {e}\n"
    return url, log

def get_bigo_hls(site_id):
    urls = [
        f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}",
        f"https://ta.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}",
    ]
    logs = ""
    for api_url in urls:
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=10)
            logs += f"API {site_id}: {api_url} {r.status_code}\n"
            if r.status_code==200:
                m = re.search(r"https?://[^\s\"']+\.m3u8[^\s\"']*", r.text)
                if m:
                    return m.group(0), logs+f"เจอ HLS {m.group(0)[:120]}\n"
                try:
                    j=r.json()
                    def find(o):
                        if isinstance(o,str) and ".m3u8" in o: return o
                        if isinstance(o,dict):
                            for v in o.values():
                                x=find(v)
                                if x: return x
                        if isinstance(o,list):
                            for v in o:
                                x=find(v)
                                if x: return x
                        return None
                    f=find(j)
                    if f: return f, logs+"เจอใน json\n"
                except: pass
        except Exception as e:
            logs+=f"err {e}\n"
    return None, logs

@app.route("/")
def home(): return HTML_PAGE

@app.route("/api/start", methods=["POST"])
def api_start():
    data=request.json
    raw=data.get("url","")
    # extract first url
    m=re.search(r"https?://[^\s]+", raw)
    raw_url=m.group(0).replace(')','').strip() if m else raw
    quality=data.get("quality","best")
    job_id=uuid.uuid4().hex[:8]

    resolved, slink_log = resolve_slink(raw_url)
    cleaned = resolved.split("?")[0].split("&")[0].rstrip("/")
    
    # extract siteID
    mm=re.search(r"/sid/(\d+)_", cleaned)
    if not mm: mm=re.search(r"bigo\.tv/(\d+)", cleaned)
    site_id=mm.group(1) if mm else "unknown"

    out=os.path.join(RECORD_DIR, f"{job_id}.mp4")
    jobs[job_id]={"id":job_id,"url":raw_url,"resolved":cleaned,"siteid":site_id,"quality":quality,"status":"starting","log":slink_log,"time":datetime.now().strftime("%H:%M:%S %d/%m"),"file":out}

    def run():
        try:
            jobs[job_id]["status"]="recording"
            log=slink_log+f"\nResolved URL: {cleaned}\nSiteID: {site_id}\n"
            if "bigo.tv" in cleaned and site_id!="unknown":
                hls, api_log = get_bigo_hls(site_id)
                log+=api_log
                if hls:
                    log+=f"\nเจอ HLS จริง! เริ่มอัดด้วย ffmpeg\n{hls[:150]}\n"
                    jobs[job_id]["log"]=log
                    cmd=["ffmpeg","-y","-user_agent",HEADERS["User-Agent"],"-referer","https://www.bigo.tv/","-i",hls,"-c","copy",out]
                    proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in proc.stdout:
                        jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-6000:]
                    proc.wait()
                    jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
                    return
                else:
                    log+="\nไม่เจอ HLS จาก API จะลอง yt-dlp ต่อ (ถ้ายัง not live แสดงว่า Bigo บล็อก IP นี้จริงๆ ต้องรอช่องไลฟ์ใหม่)\n"
            # fallback yt-dlp
            q_map={"best":"best","1080p":"best[height<=1080]","720p":"best[height<=720]","480p SD":"best[height<=480]"}
            fmt=q_map.get(quality,"best")
            cmd=["yt-dlp","--no-check-certificate","--no-playlist","-f",fmt,"-o",out,"--merge-output-format","mp4",cleaned]
            log+=f"CMD yt-dlp {cleaned}\n"
            jobs[job_id]["log"]=log
            proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-6000:]
            proc.wait()
            jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
        except Exception as e:
            jobs[job_id]["log"]+=str(e)
            jobs[job_id]["status"]="error"
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"id":job_id,"resolved":cleaned,"siteid":site_id,"raw":raw_url})

@app.route("/api/list")
def api_list(): return jsonify(list(jobs.values())[::-1])

if __name__=="__main__": app.run(host="0.0.0.0", port=5000)
