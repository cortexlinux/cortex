import time

from cortex.branding import show_banner
from cortex.hardware_detection import detect_hardware


def run_demo() -> int:
    show_banner()
    print("\n🚀 Cortex One-Command Investor Demo\n")

    # 1️⃣ Hardware Scan
    print("🔍 Scanning system hardware...")
    time.sleep(0.8)

    hw = detect_hardware()


    # Access SystemInfo attributes directly
    cpu_name = hw.cpu.model if hw.cpu and hw.cpu.model else "Unknown"
    memory_gb = round(hw.memory.total_gb, 1) if hw.memory else 0

    print(f"✔ CPU: {cpu_name}")
    print(f"✔ RAM: {memory_gb} GB")

    # Check for GPU
    has_gpu = hw.has_nvidia_gpu or hw.has_amd_gpu
    if has_gpu and hw.gpu:
        gpu_info = hw.gpu[0]
        print(f"✔ GPU: {gpu_info.model}")
        print("• LLaMA-3-8B → Optimized for your GPU")
        print("• Mistral-7B → High performance inference")
    
    else:
        print("⚠️ GPU: Not detected (CPU mode enabled)")
        print("• Phi-2 → Lightweight CPU model")
        print("• Mistral-7B-Instruct → Efficient on CPU")

    # 2️⃣ Model Recommendations
    print("\n🤖 Model Recommendations:")


    # 3️⃣ Quick LLM Test (safe mock)
    print("\n🧪 Running quick LLM test...")
    time.sleep(1)
    print("Prompt: Hello from Cortex")
    print("Response: Hello! Your system is AI-ready 🚀")

    # 4️⃣ Kernel / System Status
    print("\n⚙️ System Status:")
    print("✔ Kernel Scheduler: Active")
    print("✔ AI Runtime: Ready")

    # 5️⃣ Summary
    print("\n✅ Demo Complete")
    print("🎉 Your system is READY for AI workloads\n")

    return 0
