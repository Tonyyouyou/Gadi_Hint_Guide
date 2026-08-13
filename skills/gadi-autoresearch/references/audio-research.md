# Audio Research Adapter Pack

## Contents

1. Task families
2. Model families
3. Research routes
4. Evidence protocols
5. Human and perceptual evidence
6. Safety and integrity
7. Inode-safe audio

## Task Families

Treat audio as several related scientific domains, not as an AudioLLM synonym.

| Adapter | Includes | Distinguishing questions |
|---|---|---|
| `audio.speech-understanding` | ASR, translation, diarization, speaker/language/emotion, SLU | Acoustic-linguistic alignment, overlap, duration, noise, domain, language. |
| `audio.speech-generation` | TTS, voice conversion, expressive speech, singing | Intelligibility, identity, prosody, emotion, duration, naturalness. |
| `audio.speech-interaction` | Speech-to-speech, duplex dialogue, interruption | First response, turn-taking, buffering, error propagation, perceived responsiveness. |
| `audio.general-understanding` | Events, captioning, QA, temporal/spatial grounding | Polyphony, timing, scene relations, rare events, spatial cues. |
| `audio.general-generation` | Text-to-audio, Foley, effects, editing, spatial generation | Prompt alignment, event timing, edit locality, diversity, perceptual quality. |
| `audio.music-understanding` | Transcription, retrieval, structure, source analysis, MIR | Rhythm, harmony, form, instrumentation, cultural and genre transfer. |
| `audio.music-generation` | Composition, accompaniment, songs, multitrack, long-form editing | Motif, form, rhythm, harmony, control, originality, long-range coherence. |
| `audio.signal-processing` | Enhancement, separation, dereverb, restoration, codecs | Distortion, perception, downstream utility, bitrate, interference, domain. |
| `audio.language-multimodal` | AudioLLMs, SpeechLMs, audio-visual models and agents | Information loss across encoder, connector, language, and acoustic interfaces. |

When the mission is broad, map opportunities across task families with current literature and
available open assets, then deeply scout at most three high-value cells. Do not attempt one pilot
per task family.

## Model Families

Select a model adapter because it changes the mechanism and evidence, not because a model is
popular.

- `audio.encoder-discriminative`: temporal resolution, receptive field, redundancy, depth,
  streaming state, and output heads.
- `audio.seq2seq`: alignment, cross-attention, transduction, exposure, and latency.
- `audio.continuous-generation`: waveform/spectrogram phase, bandwidth, hierarchy, and acoustic
  conditioning.
- `audio.codec-autoregressive`: codec rate, multiple codebooks, delay patterns, long sequences,
  exposure error, and sequential latency.
- `audio.masked-token-generation`: confidence, masking schedule, dependency approximation, and
  iterative refinement.
- `audio.diffusion-flow`: solver path, step allocation, representation, conditioning, guidance,
  and quality-speed tradeoffs.
- `audio.vocoder-codec`: bitrate, quantization, decoder, reconstruction, perceptual loss, and
  downstream information.
- `audio.hybrid-streaming`: stage interfaces, buffers, scheduling, cascade errors, and end-to-end
  latency.

For systems research, profile the actual end-to-end path before selecting the target component:

```text
decode/load -> feature/frontend -> encoder -> connector/resampler
-> backbone/prefill -> iterative generation/decode -> codec/vocoder -> output
```

Synchronize device timing, separate warmup from steady state, and vary duration, batch, output
length, precision, model, and hardware. Treat encoder acceleration as a hypothesis until its
Amdahl ceiling is measured.

## Research Routes

Compose task, model, lever, and evidence adapters. Examples:

```text
TTS x diffusion/flow x audio preference optimization
    x controlled evidence x perceptual generation evaluation x human evaluation

Music generation x codec autoregressive x architecture
    x controlled evidence x music structure x perceptual evaluation x memorization safety

ASR x encoder-discriminative x systems
    x reference task evaluation x system measurement
```

Use `audio.generative-quality-control` for methods whose claim changes perceived synthesis quality
or controllability, and `audio.preference-optimization` for RL/preference work on generated audio.
Both require real human evidence. Use `core.systems` instead for an exact or quality-preserving
inference acceleration claim; generation task/model adapters alone do not force a listening study.

For optimization or RL, start from observed dynamics rather than a generic algorithm name.
Inspect reward calibration, reward hacking, on/off-policy mismatch, acoustic versus linguistic
credit assignment, length effects, KL/entropy, collapse, sample efficiency, and seed variance.
Removing the audio input or replacing the task reward with a generic text reward should materially
change the proposed mechanism; otherwise classify it as a transfer.

For representation or codec research, measure both reconstruction and task information. Separate
bitrate or sequence-length savings from changes in model capacity and training compute.

For generation control, predeclare prompt/reference conditions, sampling budget, seeds, duration,
and edit region. Never choose samples after seeing all methods.

## Evidence Protocols

### Reference Tasks

Use real ground truth and immutable splits. Report aggregate metrics plus predeclared slices such
as duration, language, speaker, overlap, noise, event density, genre, or domain. Deduplicate at the
recording and semantic-content levels before selection.

### Signal Transformation

Combine signal-reference metrics with a perceptual or downstream task. Check whether a metric was
also optimized by the method and whether improvements survive unseen distortions and domains.
Separate hallucinated content from restoration.

### Generation

Use fixed prompts/references, identical generation budgets, multiple seeds, and blinded sample
identity. Evaluate distinct claims separately: acoustic quality, semantic alignment, identity,
prosody, control, diversity, temporal structure, musical structure, and originality. A single
embedding score cannot validate all dimensions.

### Interactive and Streaming

Report first output, final latency, real-time factor, throughput, memory, quality, and interruption
behavior under declared load. Include frontend, network/IPC when relevant, model stages, codec,
and audio buffering. Do not substitute offline kernel latency for interaction latency.

### Music

Evaluate local acoustics separately from rhythm, harmony, motif, section/form, instrumentation,
prompt control, and long-range coherence. Include cross-genre and cross-cultural limitations.
Compare symbolic and waveform claims only through metrics valid for both representations.

## Human and Perceptual Evidence

Perceptual generation claims commonly require real listeners. Objective metrics can prioritize
discovery probes only when their calibration and target population match the claim.

Before requesting ratings, freeze:

- hypotheses and primary perceptual dimensions
- prompt/reference/sample selection and random seeds
- baseline identities and generation budgets
- blinded randomization, headphones or listening conditions, exclusions, and quality checks
- rater population, consent/ethics requirements, sample size, and statistical analysis

Generate the study bundle automatically, then hand off to `waiting_human`. Do not manufacture MOS,
MUSHRA, ABX, preference, demographic, consent, or annotation records. If no human evidence can be
obtained, lower the claim ceiling and do not finish a perceptual paper as though the study existed.

## Safety and Integrity

Audio data may carry identity, biometric, copyrighted, cultural, and private information. Record
license and consent constraints before acquisition or generation.

- Split by speaker, recording session, source work, song, stem, prompt origin, and near-duplicate
  content as applicable. Random clips from one source do not create independent train/test data.
- Test generated speech for identity leakage and unauthorized voice imitation when relevant.
- Test music and open-ended generation for near-copying, memorized lyrics/melodies, and benchmark
  contamination using content-level methods, not filenames alone.
- Report sample rate, channels, loudness handling, resampling, clipping, duration, and codec path.
- Treat evaluator models as fallible measurements; check domain, language, genre, and cultural
  bias before using their scores as evidence.
- Keep harmful or identity-sensitive samples access-controlled and publish only what the recorded
  permissions allow.

## Inode-Safe Audio

Never publish one durable file per utterance, prompt, seed, frame, generated sample, or rating.

1. Download, decode, resample, generate, and extract features only in `$PBS_JOBFS`.
2. Store source datasets as a controlled number of coarse archives or streamable shards under
   `/g/data/wa66/Xiangyu/Data`.
3. During experiments, aggregate metrics and per-example records into one compact table.
4. Publish generated media as `audio-samples.tar.zst` plus one manifest and checksum. Retain only
   a small declared listening/demo subset separately when necessary.
5. Store human-study stimuli as one blinded archive and returned ratings as one compact table.
6. Keep only bounded checkpoints; archive or consolidate multirank and per-sample output before
   jobfs disappears.
7. Build every expanded environment in jobfs and publish only the tested `.sqsh` under
   `/g/data/wa66/Xiangyu/enviroment_cache`.

The manifest should record logical sample ID, archive member, source split, prompt/reference ID,
method, seed, duration, sample rate, channels, checksum, and publication permission. The campaign's
declared output-entry ceiling counts the archive, manifest, metrics, logs, and selected examples.
