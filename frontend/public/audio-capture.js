// AudioWorklet: mono audio -> 16 kHz PCM16, 80 ms frames. Never records to a file.
class JarvisCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.remaining = this.ratio;
    this.sum = 0;
    this.offset = 0;
    this.frame = new ArrayBuffer(2560);
    this.view = new DataView(this.frame);
    this.energy = 0;
  }
  process(inputs) {
    const channels = inputs[0];
    if (!channels?.length) return true;
    for (let index = 0; index < channels[0].length; index++) {
      let sample = 0;
      for (const channel of channels) sample += channel[index] / channels.length;
      let weight = 1;
      while (weight > 0.000001) {
        const used = Math.min(weight, this.remaining);
        this.sum += sample * used;
        this.remaining -= used;
        weight -= used;
        if (this.remaining < 0.000001) {
          const value = Math.max(-1, Math.min(1, this.sum / this.ratio));
          this.view.setInt16(this.offset * 2, Math.round(value * 32767), true);
          this.energy += value * value;
          if (++this.offset === 1280) {
            this.port.postMessage({ pcm: this.frame, level: Math.sqrt(this.energy / 1280) }, [this.frame]);
            this.frame = new ArrayBuffer(2560);
            this.view = new DataView(this.frame);
            this.offset = 0;
            this.energy = 0;
          }
          this.sum = 0;
          this.remaining = this.ratio;
        }
      }
    }
    return true;
  }
}
registerProcessor('jarvis-capture', JarvisCapture);
