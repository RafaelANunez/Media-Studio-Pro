@echo off
:: Activate your Anaconda environment for CodeFormer
call conda activate codeformer

:: Run inference on the folder passed by the Python script (%1)
:: --w 0.5 balances detail retention vs restoration
python "C:\AI\CodeFormer\inference_codeformer.py" -w 0.5 --input_path %1 --face_upsample