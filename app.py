
import os, re, requests, subprocess, threading, uuid, json, base64
from flask import Flask, request, jsonify
from datetime import datetime
app=Flask(__name__)
jobs={}
def get_html_file():
    try: return open('index.html','r',encoding='utf-8').read()
    except: return "OK"

HEADERS={
"User-Agent":"Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
"Referer":"https://www.bigo.tv/",
"Origin":"https://www.bigo.tv",
"Accept-Language":"th-TH,th;q=0.9,en;q=0.8",
"Accept":"*/*"
}

def resolve_any(url):
    log=""; url=url.strip()
    if re.match(r"^\d+$", url): url=f"https://www.bigo.tv/th/{url}"; log+=f"ID->{url}\n"
    if not url.startswith("http") and re.match(r"^[A-Za-z0-9_\.]+$", url): url=f"https://www.bigo.tv/{url}"; log+=f"user->{url}\n"
    if "slink" in url or "onelink" in url:
        try:
            r=requests.Session().get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            log+=f"slink {r.status_code}->{r.url}\n"
            m=re.search(r"https://www\.bigo\.tv/sid/[^\"\'\s<>\\]+", r.text)
            if m: 
                sid=m.group(0).replace("\\u002F","/").split('"')[0]
                return sid, log+f"found sid from slink html\n"
            if "bigo.tv/sid/" in r.url: return r.url, log
            return r.url, log
        except Exception as e: return url, log+f"err {e}\n"
    return url, log

def extract_hls_live(sid_url):
    log=""
    # keep full query string
    # sid_url example: https://www.bigo.tv/sid/2920899939_1827326406_1792832429?c=0&p=2&t=0&b=982093669&h=1140986432&mk=v2.xxx
    m_sid = re.search(r"/sid/([^?]+)", sid_url)
    m_qs = sid_url.split("?",1)[1] if "?" in sid_url else ""
    params = {}
    for kv in m_qs.split("&"):
        if "=" in kv:
            k,v = kv.split("=",1)
            params[k]=v

    site_id_full = m_sid.group(1) if m_sid else ""
    site_id = site_id_full.split("_")[0] if "_" in site_id_full else site_id_full
    b = params.get("b","")
    h = params.get("h","")
    mk = params.get("mk","")
    p = params.get("p","2")
    t = params.get("t","0")
    c = params.get("c","0")

    log+=f"site_id={site_id} full={site_id_full}\n"
    log+=f"b={b} h={h} mk={mk[:20]}...\n"
    log+=f"p={p} t={t} c={c}\n"

    # 1. Try get page with full URL (with b/h/mk) - important
    try:
        r=requests.get(sid_url, headers=HEADERS, timeout=15)
        log+=f"GET full sid URL {r.status_code} len {len(r.text)}\n"
        txt=r.text.replace("\\u002F","/")
        # deep search
        patterns = [
            r"https?://[^\"\'\s<>]+\.m3u8[^\"\'\s<>]*",
            r"https?://[^\"\'\s<>]+\.flv[^\"\'\s<>]*",
            r'"hls":"([^"]+\.m3u8[^"]*)"',
            r'"flv":"([^"]+\.flv[^"]*)"',
            r'hls\":\"([^"]+m3u8[^"]*)',
        ]
        for pat in patterns:
            found=re.findall(pat, txt)
            if found:
                log+=f"pattern {pat} found {len(found)}\n"
                for f in found[:3]:
                    clean=f.replace("\\u002F","/").replace("\\","")
                    if "http" in clean:
                        log+=f"FOUND in HTML: {clean[:200]}\n"
                        return clean, log+"FOUND in HTML\n", "live"
        # try json in window
        m_json = re.search(r"window\._\$store\s*=\s*(\{.+?\});", txt)
        if m_json:
            try:
                j=json.loads(m_json.group(1))
                log+=f"_store keys {list(j.keys())[:10]}\n"
            except: pass
    except Exception as e:
        log+=f"page err {e}\n"

    # 2. Try official APIs with b/h
    apis=[]
    base_params = f"siteId={site_id}"
    if b: base_params+=f"&b={b}"
    if h: base_params+=f"&h={h}"
    if mk: base_params+=f"&mk={mk}"
    # try many endpoints
    apis.append(f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?{base_params}")
    apis.append(f"https://ta.bigo.tv/official_website/studio/getInternalStudioInfo?{base_params}")
    apis.append(f"https://www.bigo.tv/official_website/studio/getExternalStudioInfo?siteId={site_id}")
    apis.append(f"https://www.bigo.tv/official_website/studio/getStudioInfo?siteId={site_id}&b={b}&h={h}")
    apis.append(f"https://www.bigo.tv/openOfficialWeb/getUserInfo?bigoId={h}")
    apis.append(f"https://bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}&b={b}&h={h}")

    for api in apis:
        try:
            rr=requests.get(api, headers=HEADERS, timeout=10)
            log+=f"API {api[:120]} -> {rr.status_code} len {len(rr.text)}\n"
            if rr.status_code==200:
                # find m3u8
                mm=re.search(r"https?://[^\"\'\s<>]+\.m3u8[^\"\'\s<>]*", rr.text.replace("\\u002F","/"))
                if mm:
                    clean=mm.group(0).replace("\\u002F","/").split('"')[0]
                    log+=f"FOUND via API: {clean[:200]}\n"
                    return clean, log+f"FOUND via {api[:80]}\n", "live"
                try:
                    jj=json.loads(rr.text)
                    # dump keys
                    log+=f"API JSON keys: {str(jj)[:500]}\n"
                    # recursive search for hls
                    def find_hls(obj):
                        if isinstance(obj, dict):
                            for v in obj.values():
                                r=find_hls(v)
                                if r: return r
                            # direct
                            if 'hls' in obj and obj['hls']:
                                return obj['hls']
                            if 'flv' in obj and obj['flv']:
                                return obj['flv']
                            if 'alive' in obj and obj['alive']==False:
                                return "OFFLINE_FLAG"
                        elif isinstance(obj, list):
                            for item in obj:
                                r=find_hls(item)
                                if r: return r
                        elif isinstance(obj, str) and ".m3u8" in obj:
                            return obj
                        return None
                    found=find_hls(jj)
                    if found and found!="OFFLINE_FLAG" and ".m3u8" in found:
                        return found, log+"FOUND in JSON\n", "live"
                    if found=="OFFLINE_FLAG":
                        log+="API says OFFLINE\n"
                except Exception as je:
                    log+=f"json parse err {je} - text {rr.text[:300]}\n"
        except Exception as e:
            log+=f"API err {api[:60]} {e}\n"

    # 3. Try yt-dlp direct as last resort to get m3u8 url via --print url
    try:
        log+="Trying yt-dlp --print urls\n"
        proc=subprocess.Popen(["yt-dlp","-g",sid_url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out, _ = proc.communicate(timeout=15)
        log+=f"yt-dlp -g out: {out[:500]}\n"
        if ".m3u8" in out:
            m=re.search(r"https?://[^\s]+\.m3u8[^\s]*", out)
            if m:
                return m.group(0), log+"FOUND via yt-dlp -g\n", "live"
    except Exception as e:
        log+=f"yt-dlp -g err {e}\n"

    return None, log, "offline"

@app.route("/")
def home(): return get_html_file()

@app.route("/api/start", methods=["POST"])
def api_start():
    data=request.json; raw=data.get("url","")
    mm=re.search(r"https?://[^\s]+", raw); raw_url=mm.group(0).strip(')"\'\'') if mm else raw.strip()
    resolved, slog = resolve_any(raw_url)
    mm2=re.search(r"/sid/(\d+)", resolved); site_id=mm2.group(1) if mm2 else "unknown"
    job_id=uuid.uuid4().hex[:8]
    RECORD_DIR="/tmp/recordings"; os.makedirs(RECORD_DIR, exist_ok=True)
    out=os.path.join(RECORD_DIR, f"{job_id}.mp4")
    jobs[job_id]={"id":job_id,"resolved":resolved,"siteid":site_id,"status":"checking","status_msg":"กำลังเช็คไลฟ์สดแบบใช้ b/h/mk","log":slog,"time":datetime.now().strftime("%H:%M:%S")}
    def run():
        try:
            hls, plog, state = extract_hls_live(resolved)
            log=slog+plog
            jobs[job_id]["log"]=log
            if not hls:
                jobs[job_id]["status"]="offline"
                jobs[job_id]["status_msg"]=f"ยังไม่เจอ HLS - อาจหมดอายุ mk หรือต้องใช้ลิงก์สดๆ - {site_id}"
                return
            jobs[job_id]["status"]="recording"
            jobs[job_id]["status_msg"]=f"LIVE กำลังอัด! {site_id}"
            log+=f"\nFOUND HLS LIVE {hls[:200]}\n"
            jobs[job_id]["log"]=log
            cmd=["ffmpeg","-y","-user_agent",HEADERS["User-Agent"],"-referer","https://www.bigo.tv/","-i",hls,"-c","copy","-t","10800",out]
            proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-15000:]
            proc.wait()
            jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
            jobs[job_id]["status_msg"]="done" if proc.returncode==0 else "ffmpeg error"
        except Exception as e:
            jobs[job_id]["log"]+=str(e); jobs[job_id]["status"]="error"; jobs[job_id]["status_msg"]=str(e)
    threading.Thread(target=run, daemon=True).start()
    return jsonify({"id":job_id,"resolved":resolved,"siteid":site_id,"status_msg":"กำลังเช็คไลฟ์สด..."})

@app.route("/api/list")
def api_list(): return jsonify(list(jobs.values())[::-1])

if __name__=="__main__": app.run(host="0.0.0.0", port=5000)
