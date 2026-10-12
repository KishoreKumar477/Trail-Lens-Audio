const $ = (id) => document.getElementById(id);
const camera = $("camera"), snap = $("snap"), preview = $("preview"), audio = $("audio"), questAudio = $("questAudio");
let narration = "", pocketQuest = "";
snap.onclick = () => camera.click();
camera.onchange = async () => {
  const file = camera.files[0]; if (!file) return;
  preview.src = URL.createObjectURL(file); preview.classList.add("show");
  $("capture").classList.add("has-image"); $("progress").classList.remove("hidden"); $("result").classList.add("hidden");
  const form = new FormData(); form.append("file", file);
  const send = async (lat = 0, lng = 0) => { form.append("lat", lat); form.append("lng", lng); await identify(form); };
  navigator.geolocation?.getCurrentPosition(p => send(p.coords.latitude, p.coords.longitude), () => send(), {timeout: 6000}) || send();
};
async function identify(form) {
  try { const response = await fetch("/api/identify", {method:"POST", body:form}); const data = await response.json(); if (!response.ok) throw new Error(data.detail); show(data); }
  catch (error) { $("progress").classList.add("hidden"); alert(error.message || "Unable to identify this photo. Please try again."); }
}
function show(data) {
  const a = data.analysis; narration = a.narration_script; pocketQuest = a.pocket_quest;
  $("commonName").textContent = a.common_name; $("scientificName").textContent = a.scientific_name;
  $("category").textContent = a.category + " · field finding"; $("safety").textContent = a.safety_assessment;
  $("confidence").textContent = `${a.identification_confidence || "low"} confidence`; $("confidence").className = `confidence-${a.identification_confidence || "low"}`; $("evidence").textContent = `Seen: ${a.visual_evidence || "No reliable feature detected."}`;
  $("fact").textContent = a.trail_fact; $("narration").textContent = narration; $("questText").textContent = pocketQuest; $("pocketPrompt").textContent = pocketQuest; $("mode").textContent = data.mode === "field-note demo" ? "Demo mode — add local AI to identify species." : "Identified privately on this device.";
  if (data.audio_base64) audio.src = `data:audio/${data.audio_format || "mpeg"};base64,${data.audio_base64}`;
  if (data.quest_audio_base64) questAudio.src = `data:audio/${data.quest_audio_format || "mpeg"};base64,${data.quest_audio_base64}`;
  $("progress").classList.add("hidden"); $("result").classList.remove("hidden"); $("result").scrollIntoView({behavior:"smooth", block:"nearest"});
  if (audio.src) audio.play().catch(() => {}); else speak();
}
function preferredVoice() {
  const voices = speechSynthesis.getVoices();
  const preferred = ["Samantha", "Karen", "Moira", "Daniel", "Google UK English Female", "Microsoft Jenny"];
  return preferred.map(name => voices.find(voice => voice.name.includes(name))).find(Boolean)
    || voices.find(voice => /^en(-|_)/i.test(voice.lang));
}
function speak(text) {
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 0.76;
  utterance.pitch = 0.92;
  utterance.volume = 0.9;
  const voice = preferredVoice();
  if (voice) utterance.voice = voice;
  speechSynthesis.speak(utterance);
}
if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = () => preferredVoice();
$("play").onclick = () => audio.src ? audio.play() : speak(narration);
$("startQuest").onclick = () => {
  $("pocket").classList.remove("hidden");
  if (questAudio.src) questAudio.play();
  else speak(pocketQuest);
};
$("closePocket").onclick = () => { $("pocket").classList.add("hidden"); questAudio.pause(); if ("speechSynthesis" in window) speechSynthesis.cancel(); };
