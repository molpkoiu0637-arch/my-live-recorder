
import os, re, requests, subprocess, threading, uuid, json
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)
jobs = {}

HTML = """
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>BIGO V26 FIXED</title>
<style>
body{background:#0a0a0a;color:#fff;font-family:system-ui;padding:14px}
.card{background:#1c1c1e;border-radius:18px;padding:18px;margin:14px 0;border:1px solid #2c2c2e}
input{width:100%;padding:16px;border-radius:14px;border:2px solid #ff9500;background:#2c2c2e;color:#fff;font-size:14px;box-sizing:border-box}
button{width:100%;padding:16px;border-radius:14px;border:none;font-weight:800;font-size:17px;margin:10px 0}
.btn-orange{background:#ff9500;color:#000}
.badge{background:#30d158;color:#000;padding:5px 10px;border-radius:20px;font-size:11px;font-weight:800}
pre{background:#000;padding:10px;border-radius:10px;white-space:pre-wrap;font-size:10px;max-height:600px;overflow:auto}
</style>
</head><body>
<h2>BIGO V26 <span class=badge>FIXED - BOOT OK + LIVE</span></h2>
<div class=card>
<input id=url placeholder="วาง slink.bigovideo.tv/... ตอนไลฟ์สด">
<button class=btn-orange onclick=start()>🔴 วางแล้วกดบันทึกเลย</button>
<div id=status style=font-weight:bold;margin-top:10px;font-size:13px;color:#30d158></div>
<div id=list style=margin-top:12px></div>
</div>
<script>
async function start(){
 let raw=document.getElementById('url').value.trim();
 if(!raw){alert('วางก่อน');return;}
 let url=(raw.match(/https?:\\/\\/[^\\s]+/)||[raw])[0];
 document.getElementById('status').innerHTML='⏳ กำลังขุด HLS ตอนไลฟ์สด...';
 let r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
 let j=await r.json();
 document.getElementById('status').innerHTML='✅ '+j.siteid+'<br>'+j.msg;
 load();
}
async function load(){
 let r=await fetch('/api/list'); let j=await r.json(); let h='';
 j.forEach(it=>{
  let c=it.status=='done'?'#30d158':(it.status=='recording'?'#ff9500':'#ff3b30');
  h+=`<div class=card style=border-left:5px solid ${c}><b style=color:${c}>${it.status.toUpperCase()}</b> ${it.msg}<br><small>${it.resolved.slice(0,240)}</small><pre>${(it.log||'').slice(-10000)}</pre></div>`;
 });
 document.getElementById('list').innerHTML=h;
}
setInterval(load,3000); load();
</script>
</body></html>
"""

HEADERS = {
 "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
 "Referer": "https://www.bigo.tv/",
 "Origin": "https://www.bigo.tv",
 "Accept": "*/*",
}

def resolve_url(url):
    url=url.strip()
    log=""
    if "slink" in url or "onelink" in url or "bvl" in url:
        try:
            sess=requests.Session()
            r=sess.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            log+=f"slink {r.status_code} -> {r.url} len {len(r.text)}\\n"
            m=re.search(r"https://www\\.bigo\\.tv/sid/[^\"'\\s<>\\\\]+", r.text)
            if m:
                sid=m.group(0).replace("\\u002F","/").split('"')[0]
                log+=f"found sid in slink html\\n"
                return sid, log
            if "/sid/" in r.url:
                return r.url, log
            return r.url, log
        except Exception as e:
            return url, log+f"err {e}\\n"
    return url, log

def deep_find(sid_url):
    log=""
    m=re.search(r"/sid/([^?]+)", sid_url)
    full_id=m.group(1) if m else ""
    site_id=full_id.split("_")[0] if "_" in full_id else full_id
    qs=sid_url.split("?",1)[1] if "?" in sid_url else ""
    params={}
    for kv in qs.split("&"):
        if "=" in kv:
            try: k,v=kv.split("=",1); params[k]=v
            except: pass
    b=params.get("b",""); h=params.get("h",""); mk=params.get("mk","")
    log+=f"site_id={site_id} b={b} h={h} mk={mk[:12]}...\\n"

    # GET page
    try:
        r=requests.get(sid_url, headers=HEADERS, timeout=15)
        log+=f"GET sid {r.status_code} len {len(r.text)}\\n"
        txt=r.text.replace("\\u002F","/").replace("\\/","/")
        # save
        # search all urls
        urls=re.findall(r"https?://[^\"'\\s<>]+\\.(?:m3u8|flv)[^\"'\\s<>]*", txt)
        urls=list(dict.fromkeys(urls))
        log+=f"found in page {len(urls)} m3u8/flv candidates\\n"
        for u in urls[:3]: log+=f" cand {u[:200]}\\n"
        if urls:
            return urls[0], log+"FOUND in page\\n", "live"
        # search pullUrl keywords
        for kw in ["flvPullUrl","hlsPullUrl","pullUrl","playUrl","videoUrl","liveUrl"]:
            idx=txt.find(kw)
            if idx!=-1:
                snippet=txt[max(0,idx-200):idx+600]
                mu=re.search(r"https?://[^\"'\\s<>]+\\.(?:m3u8|flv)[^\"'\\s<>]*", snippet)
                if mu:
                    log+=f"FOUND via {kw}: {mu.group(0)[:200]}\\n"
                    return mu.group(0), log+f"FOUND {kw}\\n", "live"
    except Exception as e:
        log+=f"page err {e}\\n"

    # try APIs
    apis=[
        f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}&b={b}&h={h}",
        f"https://ta.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}&b={b}&h={h}",
        f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}",
    ]
    for api in apis:
        try:
            hh=dict(HEADERS); hh["X-Requested-With"]="XMLHttpRequest"
            rr=requests.get(api, headers=hh, timeout=10)
            log+=f"API {api[:90]} -> {rr.status_code} len {len(rr.text)}\\n"
            if ".m3u8" in rr.text or ".flv" in rr.text:
                mu=re.search(r"https?://[^\"'\\s<>]+\\.(?:m3u8|flv)[^\"'\\s<>]*", rr.text.replace("\\u002F","/"))
                if mu:
                    log+=f"FOUND API {mu.group(0)[:200]}\\n"
                    return mu.group(0), log+"FOUND API\\n", "live"
            # try json parse
            try:
                j=json.loads(rr.text)
                s=json.dumps(j)
                mu=re.search(r"https?://[^\"'\\s<>]+\\.(?:m3u8|flv)[^\"'\\s<>]*", s.replace("\\u002F","/"))
                if mu:
                    return mu.group(0), log+"FOUND API JSON\\n", "live"
            except: pass
        except Exception as e:
            log+=f"API err {e}\\n"

    # yt-dlp
    try:
        log+="yt-dlp -g try\\n"
        proc=subprocess.Popen(["yt-dlp","-g",sid_url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out,_=proc.communicate(timeout=20)
        log+=f"yt-dlp out {out[:600]}\\n"
        mu=re.search(r"https?://[^\\s]+\\.(?:m3u8|flv)[^\\s]*", out)
        if mu:
            return mu.group(0), log+"FOUND yt-dlp\\n", "live"
    except Exception as e:
        log+=f"yt-dlp err {e}\\n"

    return None, log, "offline"

@app.route("/")
def home():
    return HTML

@app.route("/api/start", methods=["POST"])
def start_api():
    data=request.json
    raw=data.get("url","")
    m=re.search(r"https?://[^\\s]+", raw)
    raw_url=m.group(0).strip(')"\'') if m else raw.strip()
    resolved, slog = resolve_url(raw_url)
    ms=re.search(r"/sid/(\\d+)", resolved)
    site_id=ms.group(1) if ms else "unknown"
    job_id=uuid.uuid4().hex[:6]
    RECORD_DIR="/tmp/recordings"
    os.makedirs(RECORD_DIR, exist_ok=True)
    out=os.path.join(RECORD_DIR, f"{job_id}.mp4")
    jobs[job_id]={"id":job_id,"resolved":resolved,"siteid":site_id,"status":"checking","msg":"กำลังขุดตอนไลฟ์สด...","log":slog,"time":datetime.now().strftime("%H:%M:%S")}
    def run_job():
        try:
            hls, plog, state = deep_find(resolved)
            log=slog+plog
            jobs[job_id]["log"]=log
            if not hls:
                jobs[job_id]["status"]="offline"
                jobs[job_id]["msg"]=f"OFFLINE ยังไม่เจอ HLS - ต้องก็อปลิงก์สดๆใหม่ๆ {site_id}"
                return
            jobs[job_id]["status"]="recording"
            jobs[job_id]["msg"]=f"LIVE กำลังอัด! {site_id}"
            cmd=["ffmpeg","-y","-user_agent",HEADERS["User-Agent"],"-referer","https://www.bigo.tv/","-i",hls,"-c","copy","-t","10800",out]
            proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-15000:]
            proc.wait()
            jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
            jobs[job_id]["msg"]="done อัดเสร็จ" if proc.returncode==0 else "ffmpeg error"
        except Exception as e:
            jobs[job_id]["log"]+=str(e)
            jobs[job_id]["status"]="error"
            jobs[job_id]["msg"]=str(e)
    threading.Thread(target=run_job, daemon=True).start()
    return jsonify({"id":job_id,"resolved":resolved,"siteid":site_id,"msg":"กำลังขุด..."})

@app.route("/api/list")
def list_api():
    return jsonify(list(jobs.values())[::-1])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
