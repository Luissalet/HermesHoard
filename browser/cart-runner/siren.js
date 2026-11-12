// Offscreen page: the only place an extension may play sound without a click.
let stopAt = 0;
let context = null;

function beep() {
  if (Date.now() > stopAt) { context?.close(); context = null; return; }
  context ??= new AudioContext();
  const now = context.currentTime;
  for (const [offset, freq] of [[0, 880], [0.22, 1175], [0.44, 880]]) {
    const osc = context.createOscillator();
    const gain = context.createGain();
    osc.type = "square";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, now + offset);
    gain.gain.exponentialRampToValueAtTime(0.35, now + offset + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.18);
    osc.connect(gain).connect(context.destination);
    osc.start(now + offset);
    osc.stop(now + offset + 0.2);
  }
  setTimeout(beep, 900);
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.to !== "siren") return;
  const running = Date.now() < stopAt;
  stopAt = Date.now() + (message.seconds || 10) * 1000;
  if (!running) beep();
});
