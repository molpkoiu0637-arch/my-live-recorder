
import os, re, requests, subprocess, threading, uuid, json, urllib.parse
from flask import Flask, request, jsonify
from datetime import datetime
app = Flask(__name__)
jobs = {}

HTML_PAGE = """
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>BIGO V27 SLINK FIX</title>
<style>
body{background:#0a0a0a;color:#fff;font-family:system-ui;padding:12px}
.card{background:#1c1c1e;border-radius:18px;padding:16px;margin:12px 0;border:1px solid #2c2c2e}
input{width:100%;padding:16px;border-radius:14px;border:2px solid #ff9500;background:#2c2c2e;color:#fff;font-size:13px;box-sizing:border-box}
button{width:100%;padding:16px;border-radius:14px;border:none;font-weight:800;font-size:16px;margin:8px 0}
.btn-orange{background:#ff9500;color:#000}
.badge{background:#30d158;color:#000;padding:5px 10px;border-radius:20px;font-size:10px;font-weight:800}
pre{background:#000;padding:10px;border-radius:10px;white-space:pre-wrap;font-size:10px;max-height:700px;overflow:auto;word-break:break-all}
</style>
</head><body>
<h2>BIGO V27 <span class=badge>SLINK FIX 10355</span></h2>
<div class=card>
<input id=url placeholder="วาง slink แบบเต็มตอนไลฟ์">
<button class=btn-orange onclick=start()>วางแล้วกดบันทึกเลย V27</button>
<div id=status style=font-weight:bold;margin-top:10px;font-size:12px;color:#30d158></div>
<div id=list style=margin-top:10px></div>
</div>
<script>
async function start(){
 let raw=document.getElementById('url').value.trim();
 if(!raw){alert('วางก่อน');return;}
 let url=raw;
 if(raw.includes('http')){ let m=raw.match(/https?:\/\/[^\s]+/); if(m) url=m[0]; }
 document.getElementById('status').innerHTML='V27 แกะ slink...';
 let r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
 let j=await r.json();
 document.getElementById('status').innerHTML='site_id='+j.siteid+'<br>'+j.msg;
 load();
}
async function load(){
 let r=await fetch('/api/list'); let j=await r.json(); let h='';
 j.forEach(it=>{
  let c=it.status=='done'?'#30d158':(it.status=='recording'?'#ff9500':'#ff3b30');
  h+=`<div class=card style=border-left:5px solid ${c}><b style=color:${c}>${it.status.toUpperCase()}</b> ${it.msg}<br><small>${it.resolved.slice(0,300)}</small><pre>${(it.log||'').slice(-12000)}</pre></div>`;
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
}

def resolve_slink(slink_url):
    log=""
    m_code=re.search(r"slink\.bigovideo\.tv/([A-Za-z0-9]+)", slink_url)
    code=m_code.group(1) if m_code else ""
    log+=f"code={code}\n"
    try:
        r=requests.get(slink_url, headers=HEADERS, allow_redirects=False, timeout=10)
        loc=r.headers.get("Location","")
        log+=f"no-redirect {r.status_code} Location={loc[:200]}\n"
        if loc and "bigo.tv" in loc:
            return loc, log+"FOUND via Location\n"
    except Exception as e:
        log+=f"no-redirect err {e}\n"
    try:
        r=requests.get(slink_url, headers=HEADERS, timeout=15, allow_redirects=True)
        log+=f"GET slink {r.status_code} final {r.url} len {len(r.text)}\n"
        txt=r.text
        # use simple pattern without quotes
        m=re.search(r"https://www\.bigo\.tv/sid/[^\s<>]+", txt)
        if m:
            found=m.group(0).replace("\u002F","/").replace("\/","/")
            found=urllib.parse.unquote(found).split('"')[0].split("'")[0]
            log+=f"FOUND sid pattern {found[:200]}\n"
            return found, log+"FOUND pattern\n"
        if "bigo.tv" in r.url and r.url!=slink_url:
            return r.url, log+"final url is bigo\n"
        return slink_url, log+"no sid in html\n"
    except Exception as e:
        return slink_url, log+f"err {e}\n"

def deep_find(sid_url):
    log=""
    m=re.search(r"/sid/([^?]+)", sid_url)
    full_id=m.group(1) if m else ""
    site_id=full_id.split("_")[0] if "_" in full_id else full_id
    qs=sid_url.split("?",1)[1] if "?" in sid_url else ""
    params={}
    for kv in qs.split("&"):
        if "=" in kv:
            try:
                k,v=kv.split("=",1)
                params[k]=v
            except:
                pass
    b=params.get("b","")
    h=params.get("h","")
    log+=f"parse site_id={site_id} b={b} h={h}\n"
    if not site_id:
        m2=re.search(r"bigo\.tv/(?:th/)?(\d+)", sid_url)
        if m2:
            site_id=m2.group(1)
    try:
        r=requests.get(sid_url, headers=HEADERS, timeout=15)
        log+=f"GET sid {r.status_code} len {len(r.text)}\n"
        txt=r.text.replace("\u002F","/")
        urls=re.findall(r"https?://[^\s<>]+\.(?:m3u8|flv)[^\s<>]*", txt)
        urls=list(dict.fromkeys(urls))
        log+=f"page found {len(urls)} candidates\n"
        if urls:
            return urls[0].split('"')[0].split("'")[0], log+"FOUND page\n", "live"
        for kw in ["flvPullUrl","hlsPullUrl","pullUrl"]:
            idx=txt.find(kw)
            if idx!=-1:
                snippet=txt[max(0,idx-300):idx+700]
                mu=re.search(r"https?://[^\s<>]+\.(?:m3u8|flv)[^\s<>]*", snippet)
                if mu:
                    return mu.group(0).split('"')[0], log+f"FOUND {kw}\n", "live"
    except Exception as e:
        log+=f"page err {e}\n"
    apis=[]
    if site_id and b and h:
        apis.append(f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}&b={b}&h={h}")
        apis.append(f"https://ta.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}&b={b}&h={h}")
    if site_id:
        apis.append(f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}")
    for api in apis:
        try:
            hh=dict(HEADERS)
            hh["X-Requested-With"]="XMLHttpRequest"
            rr=requests.get(api, headers=hh, timeout=10)
            log+=f"API {api[:90]} -> {rr.status_code} len {len(rr.text)}\n"
            if ".m3u8" in rr.text or ".flv" in rr.text:
                mu=re.search(r"https?://[^\s<>]+\.(?:m3u8|flv)[^\s<>]*", rr.text.replace("\u002F","/"))
                if mu:
                    return mu.group(0).split('"')[0], log+"FOUND API\n", "live"
        except Exception as e:
            log+=f"API err {e}\n"
    try:
        proc=subprocess.Popen(["yt-dlp","-g",sid_url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out,_=proc.communicate(timeout=20)
        log+=f"yt-dlp -g {out[:600]}\n"
        mu=re.search(r"https?://[^\s]+\.(?:m3u8|flv)[^\s]*", out)
        if mu:
            return mu.group(0), log+"FOUND yt-dlp\n", "live"
    except Exception as e:
        log+=f"yt-dlp err {e}\n"
    return None, log, "offline"

@app.route("/")
def home():
    return HTML_PAGE

@app.route("/api/start", methods=["POST"])
def start_api():
    data=request.json
    raw=data.get("url","").strip()
    m=re.search(r"https://[^\s<>]+", raw)
    raw_url=m.group(0) if m else raw
    resolved=""; slog=""
    if "slink" in raw_url:
        resolved, slog = resolve_slink(raw_url)
    else:
        resolved, slog = raw_url, ""
    if "slink" in resolved:
        r2,s2=resolve_slink(resolved)
        resolved=r2
        slog+=s2
    ms=re.search(r"/sid/(\d+)", resolved)
    if ms:
        site_id=ms.group(1)
    else:
        ms2=re.search(r"/(?:th/)?(\d+)", resolved)
        site_id=ms2.group(1) if ms2 else "unknown"
    job_id=uuid.uuid4().hex[:6]
    RECORD_DIR="/tmp/recordings"
    os.makedirs(RECORD_DIR, exist_ok=True)
    out=os.path.join(RECORD_DIR, f"{job_id}.mp4")
    jobs[job_id]={"id":job_id,"resolved":resolved,"siteid":site_id,"status":"checking","msg":"V27 แกะ slink 10355...","log":slog,"time":datetime.now().strftime("%H:%M:%S")}
    def run_job():
        try:
            hls, plog, state = deep_find(resolved)
            log=slog+plog
            jobs[job_id]["log"]=log
            if not hls:
                jobs[job_id]["status"]="offline"
                jobs[job_id]["msg"]=f"OFFLINE {site_id}"
                return
            jobs[job_id]["status"]="recording"
            jobs[job_id]["msg"]=f"LIVE {site_id}"
            cmd=["ffmpeg","-y","-user_agent",HEADERS["User-Agent"],"-referer","https://www.bigo.tv/","-i",hls,"-c","copy","-t","10800",out]
            proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-15000:]
            proc.wait()
            jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
            jobs[job_id]["msg"]="done" if proc.returncode==0 else "ffmpeg error"
        except Exception as e:
            jobs[job_id]["log"]+=str(e)
            jobs[job_id]["status"]="error"
            jobs[job_id]["msg"]=str(e)
    threading.Thread(target=run_job, daemon=True).start()
    return jsonify({"id":job_id,"resolved":resolved,"siteid":site_id,"msg":"V27 กำลังขุด..."})

@app.route("/api/list")
def list_api():
    return jsonify(list(jobs.values())[::-1])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
