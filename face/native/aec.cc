// JARVIS — envoltorio C mínimo del cancelador de eco WebRTC AEC3 (webrtc-audio-processing-1, el mismo que usa
// el módulo echo-cancel de PipeWire). face lo carga con ctypes (jarvis/eco.py). 16 kHz, mono, tramas de 10 ms.
// Compilar: scripts/install-face.sh (g++ -O2 -shared -fPIC aec.cc $(pkg-config ... webrtc-audio-processing-1)).
#include <modules/audio_processing/include/audio_processing.h>
#include <cstdint>

extern "C" {

struct jaec { webrtc::AudioProcessing* apm; webrtc::StreamConfig sc; };

// ns: supresión de ruido (0 = no; puede hacer alucinar a Whisper). hpf: filtro paso alto.
jaec* jaec_new(int rate, int ns, int hpf) {
  auto* a = new jaec{webrtc::AudioProcessingBuilder().Create(), webrtc::StreamConfig(rate, 1)};
  a->apm->AddRef();  // objeto con cuenta de referencias: se libera con Release()
  webrtc::AudioProcessing::Config c;
  c.echo_canceller.enabled = true;
  c.echo_canceller.mobile_mode = false;
  c.high_pass_filter.enabled = hpf != 0;
  c.noise_suppression.enabled = ns != 0;
  c.gain_controller1.enabled = false;
  c.gain_controller2.enabled = false;
  a->apm->ApplyConfig(c);
  return a;
}

// ref: lo que sonó por los altavoces (monitor del sink) en esta trama; mic: lo captado. out: mic sin eco.
// delay_ms: retardo aproximado ref→mic (AEC3 lo afina solo). Devuelve 0 si todo fue bien.
int jaec_process(jaec* a, const int16_t* ref, const int16_t* mic, int16_t* out, int delay_ms) {
  int16_t tmp[480];
  int r = a->apm->ProcessReverseStream(ref, a->sc, a->sc, tmp);
  a->apm->set_stream_delay_ms(delay_ms);
  return r | a->apm->ProcessStream(mic, a->sc, a->sc, out);
}

// ERLE (dB) y retardo estimado (ms); -1 si aún no hay dato.
void jaec_stats(jaec* a, double* erle, int* delay) {
  auto s = a->apm->GetStatistics();
  *erle = s.echo_return_loss_enhancement ? *s.echo_return_loss_enhancement : -1.0;
  *delay = s.delay_ms ? *s.delay_ms : -1;
}

void jaec_free(jaec* a) { a->apm->Release(); delete a; }
}
