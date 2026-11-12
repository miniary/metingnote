import 'dotenv/config';
import express from 'express';
import multer from 'multer';
import { randomUUID } from 'node:crypto';
import { mkdir, readdir, readFile, writeFile, unlink } from 'node:fs/promises';
import path from 'node:path';
import { GoogleGenAI, Type, createPartFromUri } from '@google/genai';

const { GEMINI_API_KEY, GEMINI_MODEL = 'gemini-3.1-flash-lite', PORT = 3000 } = process.env;

if (!GEMINI_API_KEY) {
  console.error('[오류] .env 파일에 GEMINI_API_KEY를 입력하세요.');
  process.exit(1);
}

const ai = new GoogleGenAI({ apiKey: GEMINI_API_KEY });
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 500 * 1024 * 1024 } });
const app = express();

app.use(express.json({ limit: '10mb' }));
app.use(express.static('public'));

// ---------- 재시도 ----------

const MAX_RETRIES = 3; // 첫 시도 후 최대 3번 더 (대기: 3초 → 6초 → 12초)
const BASE_DELAY_MS = 3000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 네트워크 오류, 요청 한도 초과(429), 서버 오류(5xx)처럼 잠시 뒤 다시 하면 될 수 있는 경우만 재시도.
// 키 오류(401/403)나 잘못된 요청(400)은 다시 해도 같으므로 바로 실패 처리.
function isRetryable(err) {
  if (err?.retryable) return true;
  const status = err?.status;
  if (typeof status !== 'number') return true;
  return status === 408 || status === 429 || status >= 500;
}

async function withRetry(label, fn) {
  for (let attempt = 0; ; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (attempt >= MAX_RETRIES || !isRetryable(err)) throw err;
      const delay = BASE_DELAY_MS * 2 ** attempt;
      console.warn(`[${label}] 실패 (${err.status ?? err.message}) — ${delay / 1000}초 후 재시도 (${attempt + 1}/${MAX_RETRIES})`);
      await sleep(delay);
    }
  }
}

function friendlyError(err, fallback) {
  if (err?.status === 400 && /API key/i.test(err.message)) return 'API 키가 올바르지 않습니다. .env를 확인하세요.';
  if (err?.status === 429) return '요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.';
  return err?.message || fallback;
}

// ---------- Gemini ----------

// 인라인 전송 한도(요청 전체 20MB)를 고려해 이보다 크면 Files API로 업로드
const INLINE_LIMIT = 15 * 1024 * 1024;

const TRANSCRIBE_PROMPT = `다음 회의 녹취를 받아쓰기 해주세요.
- 들리는 그대로 원문 언어로 빠짐없이 적으세요. 요약하거나 내용을 바꾸지 마세요.
- 화자가 바뀌면 줄을 바꾸고 "화자 1:", "화자 2:" 처럼 구분하세요. 이름이 언급되면 이름을 쓰세요.
- 대략 1~2분마다 [mm:ss] 형식의 타임스탬프를 줄 앞에 붙이세요.
- 알아들을 수 없는 부분은 [불명확]으로 표시하세요.
- 받아쓰기 결과만 출력하세요.`;

const SUMMARIZE_PROMPT = `아래는 회의 받아쓰기 원문입니다. 한국어로 회의록을 정리해주세요.
- title: 회의 내용에 맞는 짧은 제목
- summary: 회의 요약 (핵심 논의 흐름을 3~6문장으로)
- decisions: 회의에서 확정된 결정 사항 목록
- actionItems: 할 일 목록. 담당자(owner)와 기한(due)은 언급된 경우에만 채우고, 없으면 빈 문자열
원문에 없는 내용은 지어내지 마세요. 해당 내용이 없으면 빈 배열로 두세요.

--- 받아쓰기 원문 ---
`;

const SUMMARY_SCHEMA = {
  type: Type.OBJECT,
  properties: {
    title: { type: Type.STRING },
    summary: { type: Type.STRING },
    decisions: { type: Type.ARRAY, items: { type: Type.STRING } },
    actionItems: {
      type: Type.ARRAY,
      items: {
        type: Type.OBJECT,
        properties: {
          task: { type: Type.STRING },
          owner: { type: Type.STRING },
          due: { type: Type.STRING },
        },
        required: ['task', 'owner', 'due'],
      },
    },
  },
  required: ['title', 'summary', 'decisions', 'actionItems'],
};

async function audioPart(file) {
  const mimeType = file.mimetype || 'audio/webm';
  if (file.size <= INLINE_LIMIT) {
    return { inlineData: { mimeType, data: file.buffer.toString('base64') } };
  }
  let uploaded = await withRetry('파일 업로드', () =>
    ai.files.upload({ file: new Blob([file.buffer], { type: mimeType }), config: { mimeType } }),
  );
  while (uploaded.state === 'PROCESSING') {
    await sleep(2000);
    uploaded = await withRetry('파일 상태 확인', () => ai.files.get({ name: uploaded.name }));
  }
  if (uploaded.state === 'FAILED') throw new Error('Gemini가 오디오 파일을 처리하지 못했습니다.');
  return createPartFromUri(uploaded.uri, uploaded.mimeType);
}

app.post('/api/transcribe', upload.single('audio'), async (req, res) => {
  try {
    if (!req.file) return res.status(400).json({ error: '녹취 파일이 없습니다.' });
    const part = await audioPart(req.file);
    const transcript = await withRetry('받아쓰기', async () => {
      const result = await ai.models.generateContent({
        model: GEMINI_MODEL,
        contents: [{ role: 'user', parts: [part, { text: TRANSCRIBE_PROMPT }] }],
      });
      const text = (result.text ?? '').trim();
      if (!text) throw Object.assign(new Error('받아쓰기 결과가 비어 있습니다.'), { retryable: true });
      return text;
    });
    res.json({ transcript });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: friendlyError(err, '받아쓰기 중 오류가 발생했습니다.') });
  }
});

app.post('/api/summarize', async (req, res) => {
  try {
    const transcript = (req.body?.transcript || '').trim();
    if (!transcript) return res.status(400).json({ error: '받아쓰기 내용이 없습니다.' });
    const notes = await withRetry('회의록 정리', async () => {
      const result = await ai.models.generateContent({
        model: GEMINI_MODEL,
        contents: SUMMARIZE_PROMPT + transcript,
        config: { responseMimeType: 'application/json', responseSchema: SUMMARY_SCHEMA },
      });
      try {
        return JSON.parse(result.text ?? '');
      } catch {
        throw Object.assign(new Error('정리 결과 형식이 올바르지 않습니다.'), { retryable: true });
      }
    });
    res.json(notes);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: friendlyError(err, '정리 중 오류가 발생했습니다.') });
  }
});

// ---------- 회의록 저장소 (data/notes/<id>.json) ----------

const NOTES_DIR = path.resolve('data', 'notes');
await mkdir(NOTES_DIR, { recursive: true });

const ID_RE = /^[0-9a-f-]{36}$/;
const notePath = (id) => path.join(NOTES_DIR, `${id}.json`);

function sanitizeNote(body) {
  const str = (v) => (typeof v === 'string' ? v : '');
  const arr = (v) => (Array.isArray(v) ? v : []);
  return {
    title: str(body.title).trim() || '제목 없는 회의',
    summary: str(body.summary),
    decisions: arr(body.decisions).map(str).filter(Boolean),
    actionItems: arr(body.actionItems)
      .map((a) => ({ task: str(a?.task), owner: str(a?.owner), due: str(a?.due) }))
      .filter((a) => a.task),
    transcript: str(body.transcript),
    fileName: str(body.fileName),
  };
}

app.get('/api/notes', async (_req, res) => {
  const files = (await readdir(NOTES_DIR)).filter((f) => f.endsWith('.json'));
  const notes = [];
  for (const f of files) {
    try {
      const n = JSON.parse(await readFile(path.join(NOTES_DIR, f), 'utf8'));
      notes.push({ id: n.id, title: n.title, createdAt: n.createdAt, updatedAt: n.updatedAt });
    } catch {
      // 손상된 파일은 목록에서 제외
    }
  }
  notes.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  res.json(notes);
});

app.get('/api/notes/:id', async (req, res) => {
  if (!ID_RE.test(req.params.id)) return res.status(400).json({ error: '잘못된 ID입니다.' });
  try {
    res.json(JSON.parse(await readFile(notePath(req.params.id), 'utf8')));
  } catch {
    res.status(404).json({ error: '회의록을 찾을 수 없습니다.' });
  }
});

app.post('/api/notes', async (req, res) => {
  const now = new Date().toISOString();
  const note = { id: randomUUID(), createdAt: now, updatedAt: now, ...sanitizeNote(req.body || {}) };
  await writeFile(notePath(note.id), JSON.stringify(note, null, 2), 'utf8');
  res.status(201).json(note);
});

app.put('/api/notes/:id', async (req, res) => {
  const { id } = req.params;
  if (!ID_RE.test(id)) return res.status(400).json({ error: '잘못된 ID입니다.' });
  let existing;
  try {
    existing = JSON.parse(await readFile(notePath(id), 'utf8'));
  } catch {
    return res.status(404).json({ error: '회의록을 찾을 수 없습니다.' });
  }
  const note = { id, createdAt: existing.createdAt, updatedAt: new Date().toISOString(), ...sanitizeNote(req.body || {}) };
  await writeFile(notePath(id), JSON.stringify(note, null, 2), 'utf8');
  res.json(note);
});

app.delete('/api/notes/:id', async (req, res) => {
  if (!ID_RE.test(req.params.id)) return res.status(400).json({ error: '잘못된 ID입니다.' });
  try {
    await unlink(notePath(req.params.id));
    res.status(204).end();
  } catch {
    res.status(404).json({ error: '회의록을 찾을 수 없습니다.' });
  }
});

app.listen(PORT, () => {
  console.log(`회의록 정리기 실행 중: http://localhost:${PORT}  (모델: ${GEMINI_MODEL})`);
});
