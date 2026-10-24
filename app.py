
import os, re, requests, subprocess, threading, uuid, json, urllib.parse, html as html_lib
from flask import Flask, request, jsonify
from datetime import datetime
app = Flask(__name__)
jobs = {}

HTML_PAGE = """
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>BIGO V28 CODE1 FIX</title>
<style>
body{background:#0a0a0a;color:#fff;font-family:system-ui;padding:12px}
.card{background:#1c1c1e;border-radius:18px;padding:16px;margin:12px 0;border:1px solid #2c2c2e}
input{width:100%;padding:16px;border-radius:14px;border:2px solid #00ff88;background:#2c2c2e;color:#fff;font-size:13px;box-sizing:border-box}
button{width:100%;padding:16px;border-radius:14px;border:none;font-weight:800;font-size:16px;margin:8px 0}
.btn-green{background:#00ff88;color:#000}
.badge{background:#00ff88;color:#000;padding:5px 10px;border-radius:20px;font-size:10px;font-weight:800}
pre{background:#000;padding:10px;border-radius:10px;white-space:pre-wrap;font-size:10px;max-height:700px;overflow:auto;word-break:break-all}
</style>
</head><body>
<h2>BIGO V28 <span class=badge>CODE1 FIX</span></h2>
<div class=card>
<input id=url placeholder="วาง slink ตอนไลฟ์สดๆ">
<button class=btn-green onclick=start()>V28 FIX CODE1</button>
<div id=status style=font-weight:bold;margin-top:10px;font-size:12px;color:#00ff88></div>
<div id=list style=margin-top:10px></div>
</div>
<script>
async function start(){
 let raw=document.getElementById('url').value.trim();
 let m=raw.match(/https?:\/\/[^\s]+/);
 let url=m?m[0]:raw;
 document.getElementById('status').innerHTML='V28 ส่ง c/p/t/b/h/mk ครบ...';
 let r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
 let j=await r.json();
 document.getElementById('status').innerHTML='site_id='+j.siteid+'<br>'+j.msg;
 load();
}
async function load(){
 let r=await fetch('/api/list'); let j=await r.json(); let h='';
 j.forEach(it=>{
  let c=it.status=='done'?'#00ff88':(it.status=='recording'?'#ff9500':'#ff3b30');
  h+=`<div class=card style=border-left:5px solid ${c}><b style=color:${c}>${it.status.toUpperCase()}</b> ${it.msg}<br><small>${it.resolved.slice(0,350)}</small><pre>${(it.log||'').slice(-13000)}</pre></div>`;
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
    try:
        r=requests.get(slink_url, headers=HEADERS, timeout=15, allow_redirects=True)
        log+=f"GET slink {r.status_code} final {r.url} len {len(r.text)}\n"
        txt=r.text
        txt_unescaped=html_lib.unescape(txt)
        m=re.search(r"https://www\.bigo\.tv/sid/[^\s<>]+", txt_unescaped.replace("\u002F","/"))
        if not m:
            m=re.search(r"https://www\.bigo\.tv/sid/[^\s<>]+", txt.replace("\u002F","/"))
        if m:
            found=html_lib.unescape(m.group(0)).replace("\u002F","/")
            found=urllib.parse.unquote(found)
            found=found.split('"')[0].split("'")[0].split("<")[0]
            log+=f"FOUND sid {found[:300]}\n"
            return found, log+"FOUND sid\n"
        if "bigo.tv" in r.url and r.url!=slink_url:
            return r.url, log+"final url\n"
        return slink_url, log+"no sid\n"
    except Exception as e:
        return slink_url, log+f"err {e}\n"

def deep_find(sid_url):
    log=""
    sid_url=html_lib.unescape(sid_url)
    sid_url=urllib.parse.unquote(sid_url)
    log+=f"sid_url {sid_url[:350]}\n"
    m=re.search(r"/sid/([^?]+)", sid_url)
    full_id=m.group(1) if m else ""
    site_id=full_id.split("_")[0] if "_" in full_id else full_id
    qs=sid_url.split("?",1)[1] if "?" in sid_url else ""
    qs=html_lib.unescape(qs)
    params={}
    for kv in qs.split("&"):
        if "=" in kv:
            try:
                k,v=kv.split("=",1)
                v=v.split("#")[0].split("<")[0].strip()
                params[k]=v
            except:
                pass
    b=params.get("b",""); h=params.get("h",""); mk=params.get("mk","")
    c=params.get("c","0"); p=params.get("p","2"); t=params.get("t","0")
    log+=f"parse site_id={site_id} b={b} h={h} c={c} p={p} t={t} mk={mk[:10]}..\n"
    try:
        r=requests.get(sid_url, headers=HEADERS, timeout=15)
        log+=f"GET sid {r.status_code} len {len(r.text)}\n"
        txt=html_lib.unescape(r.text).replace("\u002F","/")
        urls=re.findall(r"https?://[^\s<>]+\.(?:m3u8|flv)[^\s<>]*", txt)
        urls=list(dict.fromkeys(urls))
        log+=f"page count {len(urls)}\n"
        if urls:
            return urls[0].split('"')[0], log+"FOUND page\n", "live"
    except Exception as e:
        log+=f"page err {e}\n"
    base_q=f"siteId={site_id}&b={b}&h={h}&c={c}&p={p}&t={t}"
    if mk:
        base_q+=f"&mk={urllib.parse.quote(mk)}"
    apis=[
        f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?{base_q}",
        f"https://ta.bigo.tv/official_website/studio/getInternalStudioInfo?{base_q}",
    ]
    for api in apis:
        try:
            hh=dict(HEADERS)
            hh["X-Requested-With"]="XMLHttpRequest"
            hh["Referer"]=sid_url
            rr=requests.get(api, headers=hh, timeout=12)
            log+=f"API {api[:100]} -> {rr.status_code} len {len(rr.text)}\n"
            txt2=html_lib.unescape(rr.text).replace("\u002F","/")
            mu=re.search(r"https?://[^\s<>]+\.(?:m3u8|flv)[^\s<>]*", txt2)
            if mu:
                log+=f"FOUND API url {mu.group(0)[:200]}\n"
                return mu.group(0).split('"')[0], log+"FOUND API\n", "live"
        except Exception as e:
            log+=f"API err {e}\n"
    try:
        proc=subprocess.Popen(["yt-dlp","-g",sid_url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out,_=proc.communicate(timeout=30)
        log+=f"yt-dlp out {out[:1200]}\n"
        mu=re.search(r"https?://[^\s]+\.(?:m3u8|flv)[^\s]*", out)
        if mu:
            return mu.group(0).strip(), log+"FOUND yt-dlp\n", "live"
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
    raw_url=html_lib.unescape(raw_url)
    raw_url=raw_url.strip('"').strip("'")
    resolved=""; slog=""
    if "slink" in raw_url:
        resolved, slog = resolve_slink(raw_url)
    else:
        resolved, slog = raw_url, ""
    if "slink" in resolved and "bigo.tv/sid" not in resolved:
        r2,s2=resolve_slink(resolved)
        if "sid" in r2:
            resolved=r2
            slog+=s2
    ms=re.search(r"/sid/(\d+)", resolved)
    site_id=ms.group(1) if ms else "unknown"
    job_id=uuid.uuid4().hex[:6]
    RECORD_DIR="/tmp/recordings"
    os.makedirs(RECORD_DIR, exist_ok=True)
    out=os.path.join(RECORD_DIR, f"{job_id}.mp4")
    jobs[job_id]={"id":job_id,"resolved":resolved,"siteid":site_id,"status":"checking","msg":"V28 FIX code1...","log":slog,"time":datetime.now().strftime("%H:%M:%S")}
    def run_job():
        try:
            hls, plog, state = deep_find(resolved)
            log=slog+plog
            jobs[job_id]["log"]=log
            if not hls:
                jobs[job_id]["status"]="offline"
                jobs[job_id]["msg"]=f"OFFLINE {site_id} - mk หมดอายุ ลองก็อปใหม่สดๆ"
                return
            jobs[job_id]["status"]="recording"
            jobs[job_id]["msg"]=f"LIVE {site_id} กำลังอัด!"
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
    return jsonify({"id":job_id,"resolved":resolved,"siteid":site_id,"msg":"V28 FIX code1 กำลังแกะ..."})

@app.route("/api/list")
def list_api():
    return jsonify(list(jobs.values())[::-1])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
