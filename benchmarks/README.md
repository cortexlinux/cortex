\# Cortex JIT Benchmark Suite



This directory contains benchmarks to evaluate the impact of

Python 3.13's experimental JIT compiler on Cortex operations.



\## Benchmarks Included



1\. CLI Startup Time  

&nbsp;  Measures cold start time of the `cortex` CLI.



2\. Command Parsing  

&nbsp;  Benchmarks argparse-based command parsing overhead.



3\. Cache-like Operations  

&nbsp;  Simulates dictionary-heavy workloads similar to internal caching.



4\. Streaming  

&nbsp;  Measures generator and iteration performance.



\## How to Run



From this directory:



PYTHON\_JIT=0 python run\_benchmarks.py  

PYTHON\_JIT=1 python run\_benchmarks.py  



Or simply:



python run\_benchmarks.py



\## Findings



Python 3.13 JIT shows measurable improvements in:

\- Command parsing

\- Cache-like workloads



Streaming and startup times show minimal change, which is expected.



These results suggest Python JIT provides benefits for hot-path

operations used by Cortex.



