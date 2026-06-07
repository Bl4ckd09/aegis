import time, cupy as cp
def bw(nbytes=1<<30):  # 1GiB triad-ish: c = a + b
    n = nbytes//4
    a = cp.ones(n, cp.float32); b = cp.ones(n, cp.float32)
    cp.cuda.Stream.null.synchronize()
    t=time.perf_counter()
    for _ in range(10): c = a + b
    cp.cuda.Stream.null.synchronize()
    dt=(time.perf_counter()-t)/10
    gb=3*nbytes/1e9  # read a,b + write c
    return gb/dt
def flops(n=8192, dt_dtype=cp.float16):
    a=cp.random.rand(n,n,dtype=cp.float32).astype(dt_dtype); b=a.copy()
    cp.matmul(a,b); cp.cuda.Stream.null.synchronize()
    t=time.perf_counter()
    for _ in range(10): c=cp.matmul(a,b)
    cp.cuda.Stream.null.synchronize()
    dt=(time.perf_counter()-t)/10
    return (2*n**3)/dt/1e12
try:
    print(f"  mem bandwidth (a+b triad): {bw():.0f} GB/s")
    print(f"  FP16 matmul 8192^3       : {flops(8192, cp.float16):.1f} TFLOP/s")
    print(f"  FP32 matmul 8192^3       : {flops(8192, cp.float32):.1f} TFLOP/s")
except Exception as e:
    print("  GPU micro-benchmark failed:", str(e)[:120])
