#!/usr/bin/env python3
# LightEngine — compact EVM gas & profit helper (unique concise build)
# Modes (no argparse):
#   oracle [blocks]                 -> feeHistory percentiles & latest
#   wait <maxBaseFeeGwei> [timeout] -> block until baseFee <= target
#   plan  <profitETH> <gasUnits> [tipGwei] [headroomGwei]
#   estimate <from> <to> <dataHex> [valueETH]
# RPC endpoints: env RPC_URLS="https://rpc1,https://rpc2"

import os, sys, json, time, math
from urllib.request import Request, urlopen

def urls():
    xs = [x.strip() for x in os.environ.get("RPC_URLS","").split(",") if x.strip()]
    return xs or ["http://localhost:8545"]

def rpc(method, params=None, timeout=8):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params or []}).encode()
    last=None
    for u in urls():
        try:
            r = urlopen(Request(u, body, {"Content-Type":"application/json"}), timeout=timeout)
            out = json.loads(r.read().decode())
            if "result" in out: return out["result"]
            last = out.get("error")
        except Exception as e: last = e
    sys.exit(f"RPC failed: {last}")

PWEI = 10**18
def gwei_to_wei(x): return int(float(x)*1e9)
def wei_to_gwei(x): return (int(x))/1e9
def eth_to_wei(x):  return int(float(x)*PWEI)

def basefee():
    b = rpc("eth_getBlockByNumber", ["latest", False])
    return int(b.get("baseFeePerGas","0x0"), 16)

def maxprio():
    try: return int(rpc("eth_maxPriorityFeePerGas"),16)
    except: return gwei_to_wei(1.5)

def fee_hist(n=20, pcts=(5,20,50,80,95)):
    h = rpc("eth_feeHistory", [hex(int(n)), "latest", list(pcts)])
    base = [int(x,16) for x in h["baseFeePerGas"]][-int(n):]
    def pct(v,p):
        s=sorted(v); k=(len(s)-1)*p/100; i=math.floor(k); j=min(i+1,len(s)-1)
        return s[i] if i==j else int(s[i]+(s[j]-s[i])*(k-i))
    return {f"p{p}": round(wei_to_gwei(pct(base,p)),3) for p in pcts} | {"latest": round(wei_to_gwei(base[-1]),3)}

def cmd_oracle(a):
    n = int(a[0]) if a else 20
    print(json.dumps({"blocks":n, "baseFee_gwei": fee_hist(n)}, indent=2))

def cmd_wait(a):
    tgt = gwei_to_wei(a and a[0] or sys.exit("need maxBaseFeeGwei"))
    to  = int(a[1]) if len(a)>1 else 900
    t0=time.time()
    while True:
        bf = basefee(); g=wei_to_gwei(bf)
        print(f"baseFee={g:.3f} gwei")
        if bf<=tgt: print("GO"); return
        if time.time()-t0>to: print("TIMEOUT"); sys.exit(2)
        time.sleep(5)

def cmd_plan(a):
    if len(a)<2: sys.exit("usage: plan <profitETH> <gasUnits> [tipGwei] [headroomGwei]")
    profit, gas = float(a[0]), int(a[1])
    tip = gwei_to_wei(a[2]) if len(a)>2 else maxprio()
    head = gwei_to_wei(a[3]) if len(a)>3 else gwei_to_wei(2)
    bf = basefee()
    max_base = max(0, eth_to_wei(profit)//max(1,gas) - tip)
    out = {
      "baseFee_gwei": round(wei_to_gwei(bf),3),
      "priority_gwei": round(wei_to_gwei(tip),3),
      "break_even_baseFee_gwei": round(wei_to_gwei(max_base),3),
      "recommend": "SEND" if bf<=max_base else "WAIT",
      "suggested": {
        "maxPriorityFeePerGas_gwei": round(wei_to_gwei(tip),3),
        "maxFeePerGas_gwei": round(wei_to_gwei(bf+tip+head),3)
      }
    }
    print(json.dumps(out, indent=2))

def cmd_estimate(a):
    if len(a)<3: sys.exit("usage: estimate <from> <to> <dataHex> [valueETH]")
    from_, to, data = a[0], a[1], a[2]
    tx={"from":from_,"to":to,"data":data}
    if len(a)>3: tx["value"]=hex(eth_to_wei(a[3]))
    pr, bf = maxprio(), basefee()
    tx["maxPriorityFeePerGas"]=hex(pr); tx["maxFeePerGas"]=hex(bf+pr+gwei_to_wei(2))
    res = rpc("eth_estimateGas", [tx])
    gas = int(res,16) if isinstance(res,str) else int(res)
    cost = (gas*(bf+pr))/PWEI
    print(json.dumps({"gas":gas,"cost_eth_at_current":round(cost,8)}, indent=2))

def main():
    m = {"oracle":cmd_oracle,"wait":cmd_wait,"plan":cmd_plan,"estimate":cmd_estimate}
    if len(sys.argv)<2 or sys.argv[1] not in m:
        sys.exit("modes: oracle|wait|plan|estimate")
    m[sys.argv[1]](sys.argv[2:])

if __name__=="__main__": main()
