// MeetingNote 화면 로직. 상태는 모듈 변수로 두고 DOM 을 직접 갱신한다.
'use strict';

// ---------- 공통 도우미 ----------

// 서버 오류 코드를 사용자에게 보여 줄 문구로 바꾼다
const ERROR_MESSAGES = {
  400: '입력값을 확인해 주세요. 제목 · 일시 · 본문은 꼭 넣어야 합니다.',
  404: '회의록을 찾을 수 없습니다. 이미 지워졌을 수 있습니다.',
  413: '파일이 너무 큽니다. 25MB 이하 파일만 올릴 수 있습니다.',
  415: 'mp3 · wav 파일만 올릴 수 있습니다.',
  422: '알 수 없는 항목이 들어 있어 처리하지 못했습니다.',
  502: '받아쓰기 서비스에 연결하지 못했습니다. 잠시 뒤 다시 해 주세요.',
};

class ApiError extends Error {
  constructor(status) {
    super(ERROR_MESSAGES[status] || `처리하지 못했습니다. (오류 ${status})`);
    this.status = status;
  }
}

// /api 호출. 실패하면 ApiError 를 던진다. 204 는 null 을 돌려준다
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (err) {
    throw new Error('서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인해 주세요.');
  }
  if (!response.ok) throw new ApiError(response.status);
  if (response.status === 204) return null;
  return response.json();
}

function sendJson(method, body) {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

// 서버의 UTC 시각(…Z)을 로컬 시각 문구로 바꾼다
function formatLocalDateTime(utcIso) {
  const date = new Date(utcIso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

// 줄바꿈으로 나뉜 항목을 빈 줄 없이 배열로 만든다
function splitLines(text) {
  return (text || '').split('\n').map((line) => line.trim()).filter(Boolean);
}

// 사용자 · 서버 글은 textContent 로만 넣는다 (innerHTML 금지)
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setStatus(node, message, isError = false) {
  node.textContent = message;
  node.classList.toggle('text-rose-600', isError);
  node.classList.toggle('dark:text-rose-400', isError);
}

// ---------- 목록 ----------

let notes = [];
let listRequestSeq = 0; // 입력이 빠를 때 늦게 온 옛 응답을 버리기 위한 번호

function buildListQuery() {
  const params = new URLSearchParams();
  const q = document.getElementById('q').value.trim();
  const from = document.getElementById('from').value;
  const to = document.getElementById('to').value;
  if (q) params.set('q', q);
  if (from) params.set('from', from);
  if (to) params.set('to', to);
  // from · to 는 로컬 날짜라 시간대 차이(분)를 함께 보낸다
  if (from || to) params.set('tz_offset', String(new Date().getTimezoneOffset()));
  const query = params.toString();
  return query ? `/api/notes?${query}` : '/api/notes';
}

async function loadNotes() {
  const seq = ++listRequestSeq;
  const status = document.querySelector('[data-role="list-status"]');
  try {
    const result = await api(buildListQuery());
    if (seq !== listRequestSeq) return;
    notes = result;
    renderCards();
    const searching = document.getElementById('q').value.trim() || document.getElementById('from').value || document.getElementById('to').value;
    if (notes.length === 0) {
      setStatus(status, searching ? '조건에 맞는 회의록이 없습니다.' : '저장한 회의록이 없습니다. 「넣기」에서 첫 회의록을 만들어 보세요.');
    } else {
      setStatus(status, `회의록 ${notes.length}건`);
    }
  } catch (err) {
    if (seq !== listRequestSeq) return;
    setStatus(status, err.message, true);
  }
}

function renderCards() {
  const cards = document.getElementById('cards');
  cards.replaceChildren(...notes.map(buildCard));
}

function buildCard(note) {
  const card = el('button', 'group flex min-w-0 flex-col rounded-2xl border border-black/5 bg-white/70 p-5 text-left shadow-sm backdrop-blur-xl transition hover:-translate-y-0.5 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 dark:border-white/10 dark:bg-neutral-800/60');
  card.type = 'button';
  card.dataset.noteId = String(note.id);
  card.appendChild(el('h2', 'truncate text-base font-semibold', note.title));
  const meta = [formatLocalDateTime(note.met_at), note.attendees].filter(Boolean).join(' · ');
  card.appendChild(el('p', 'mt-1 truncate text-xs text-slate-500 dark:text-neutral-400', meta));
  const firstLine = splitLines(note.summary)[0];
  card.appendChild(el('p', 'mt-3 line-clamp-2 break-words text-sm text-slate-600 dark:text-neutral-300', firstLine || '요약 없음 (구분 실패)'));
  card.addEventListener('click', () => openModal(note.id));
  return card;
}

// ---------- 세 갈래 결과 (넣기 · 상세 공용) ----------

const PANELS = [
  { field: 'summary', label: '요약', bar: 'border-l-sky-500 dark:border-l-sky-400', text: 'text-sky-600 dark:text-sky-400' },
  { field: 'decisions', label: '결정사항', bar: 'border-l-orange-500 dark:border-l-orange-400', text: 'text-orange-600 dark:text-orange-400' },
  { field: 'todos', label: '할 일', bar: 'border-l-emerald-500 dark:border-l-emerald-400', text: 'text-emerald-600 dark:text-emerald-400' },
];

// 할 일 한 줄 「내용 | 담당자 | 기한」 을 나눈다. 기한은 말한 그대로 둔다
function parseTodoLine(line) {
  const [what = '', who = '', ...rest] = line.split('|').map((part) => part.trim());
  return { what, who: who || '미정', when: rest.join(' | ') };
}

function buildPanelItem(field, line) {
  const item = el('li', 'break-words');
  if (field !== 'todos') {
    item.textContent = line;
    return item;
  }
  const todo = parseTodoLine(line);
  item.appendChild(el('span', '', todo.what));
  const meta = [todo.who, todo.when].filter(Boolean).join(' · ');
  item.appendChild(el('span', 'block text-xs text-slate-500 dark:text-neutral-400', meta));
  return item;
}

// 세 칸을 그린다. 셋 다 비어 있으면 「구분 실패」 안내만 보여 준다
function renderPanels(container, note) {
  const allEmpty = PANELS.every((panel) => splitLines(note[panel.field]).length === 0);
  if (allEmpty) {
    const box = el('div', 'rounded-2xl border border-amber-500/30 bg-amber-50/80 p-4 text-sm text-amber-800 backdrop-blur dark:bg-amber-500/10 dark:text-amber-300');
    box.appendChild(el('p', 'font-semibold', '구분 실패'));
    box.appendChild(el('p', 'mt-1', '본문이 너무 짧거나 회의 내용이 아니어서 요약 · 결정사항 · 할 일로 나누지 못했습니다. 본문은 그대로 저장되었습니다.'));
    container.replaceChildren(box);
    return;
  }
  const grid = el('div', 'grid grid-cols-1 gap-3 md:grid-cols-3');
  PANELS.forEach((panel) => {
    const box = el('div', `min-w-0 rounded-xl border border-black/5 border-l-4 ${panel.bar} bg-white/70 p-4 shadow-sm backdrop-blur dark:border-white/10 dark:bg-neutral-800/60`);
    box.appendChild(el('h3', `text-sm font-semibold ${panel.text}`, panel.label));
    const lines = splitLines(note[panel.field]);
    if (lines.length === 0) {
      box.appendChild(el('p', 'mt-2 text-sm text-slate-400 dark:text-neutral-500', '없음'));
    } else {
      const list = el('ul', 'mt-2 list-disc space-y-1.5 pl-5 text-sm text-slate-700 dark:text-neutral-200');
      lines.forEach((line) => list.appendChild(buildPanelItem(panel.field, line)));
      box.appendChild(list);
    }
    grid.appendChild(box);
  });
  container.replaceChildren(grid);
}

// ---------- 넣기 ----------

// datetime-local 에 넣을 「지금」 로컬 시각 (YYYY-MM-DDTHH:MM)
function nowForDateTimeLocal() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

async function uploadAudio() {
  const fileInput = document.getElementById('file');
  const btnUp = document.getElementById('btnUp');
  const status = document.querySelector('[data-role="upload-status"]');
  const file = fileInput.files[0];
  if (!file) {
    setStatus(status, '먼저 mp3 · wav 파일을 고르세요.', true);
    return;
  }
  const form = new FormData();
  form.append('file', file);
  btnUp.disabled = true;
  setStatus(status, '받아쓰는 중입니다… 파일 길이에 따라 1분 넘게 걸릴 수 있습니다.');
  try {
    const result = await api('/api/upload', { method: 'POST', body: form });
    document.getElementById('body').value = result.body;
    setStatus(status, '받아쓰기를 마쳤습니다. 본문을 확인한 뒤 정리하기를 누르세요.');
  } catch (err) {
    setStatus(status, err.message, true);
  } finally {
    btnUp.disabled = false;
  }
}

async function saveNote() {
  const btnSave = document.getElementById('btnSave');
  const status = document.querySelector('[data-role="save-status"]');
  const title = document.getElementById('title').value.trim();
  const metAt = document.getElementById('metAt').value;
  const attendees = document.getElementById('attendees').value.trim();
  const body = document.getElementById('body').value.trim();

  const missing = [];
  if (!title) missing.push('제목');
  if (!metAt) missing.push('일시');
  if (!body) missing.push('본문');
  if (missing.length) {
    setStatus(status, `${missing.join(' · ')} 칸을 채워 주세요.`, true);
    return;
  }

  btnSave.disabled = true;
  setStatus(status, '저장하고 정리하는 중입니다…');
  try {
    // datetime-local 은 로컬 시각이라 UTC 로 바꿔 보낸다
    const payload = { title, met_at: new Date(metAt).toISOString(), attendees, body };
    const note = await api('/api/notes', sendJson('POST', payload));
    renderPanels(document.getElementById('result'), note);
    resetAddForm();
    setStatus(status, `저장했습니다: 「${note.title}」. 목록에서 다시 볼 수 있습니다.`);
  } catch (err) {
    setStatus(status, err.message, true);
  } finally {
    btnSave.disabled = false;
  }
}

// 저장한 뒤 같은 내용을 또 저장하지 않게 입력칸을 비운다 (결과 세 칸은 남긴다)
function resetAddForm() {
  ['title', 'attendees', 'body', 'file'].forEach((id) => { document.getElementById(id).value = ''; });
  document.getElementById('metAt').value = nowForDateTimeLocal();
  setStatus(document.querySelector('[data-role="upload-status"]'), '');
}

// ---------- 상세 (겹침 창) ----------

const DELETE_HINT = '삭제는 한 번 더 눌러야 지워집니다.';

let openNote = null; // 지금 열린 회의록 (body 포함 단건)
let deleteArmed = false; // 삭제를 한 번 눌러 둔 상태

function modalPart(role) {
  return document.querySelector(`#modal [data-role="${role}"]`);
}

function setDeleteArmed(armed) {
  deleteArmed = armed;
  modalPart('modal-delete').textContent = armed ? '한 번 더 누르면 삭제' : '삭제';
}

function renderModal() {
  modalPart('modal-title').textContent = openNote.title;
  const meta = [formatLocalDateTime(openNote.met_at), openNote.attendees || '참석자 없음'].join(' · ');
  modalPart('modal-meta').textContent = meta;
  renderPanels(modalPart('modal-panels'), openNote);
  modalPart('modal-body').textContent = openNote.body;
  document.getElementById('mTitle').value = openNote.title;
}

async function openModal(noteId) {
  try {
    openNote = await api(`/api/notes/${noteId}`);
  } catch (err) {
    // 404 면 이미 지워진 것이라 화면을 다시 부르고, 그 뒤에 안내를 남긴다
    if (err.status === 404) await refreshCurrentView();
    setStatus(currentViewStatus(), err.message, true);
    return;
  }
  renderModal();
  setDeleteArmed(false);
  setStatus(modalPart('modal-status'), DELETE_HINT);
  document.querySelector('#modal details').open = false;
  const modal = document.getElementById('modal');
  modal.classList.remove('hidden');
  modal.classList.add('flex');
  document.body.classList.add('overflow-hidden');
  modalPart('modal-close').focus();
}

function closeModal() {
  const modal = document.getElementById('modal');
  modal.classList.add('hidden');
  modal.classList.remove('flex');
  document.body.classList.remove('overflow-hidden');
  openNote = null;
  setDeleteArmed(false);
}

async function renameNote() {
  const status = modalPart('modal-status');
  const title = document.getElementById('mTitle').value.trim();
  if (!title) {
    setStatus(status, '새 제목을 넣어 주세요.', true);
    return;
  }
  // PUT 은 전 필드를 받으므로 지금 값에 제목만 바꿔 보낸다
  const payload = {
    title,
    met_at: openNote.met_at,
    attendees: openNote.attendees,
    body: openNote.body,
    summary: openNote.summary,
    decisions: openNote.decisions,
    todos: openNote.todos,
  };
  const button = modalPart('modal-rename');
  button.disabled = true;
  try {
    openNote = await api(`/api/notes/${openNote.id}`, sendJson('PUT', payload));
    renderModal();
    setStatus(status, '제목을 고쳤습니다.');
    refreshCurrentView();
  } catch (err) {
    setStatus(status, err.message, true);
  } finally {
    button.disabled = false;
  }
}

async function deleteNote() {
  const status = modalPart('modal-status');
  if (!deleteArmed) {
    setDeleteArmed(true);
    setStatus(status, '정말 지우려면 삭제를 한 번 더 누르세요.', true);
    return;
  }
  const button = modalPart('modal-delete');
  button.disabled = true;
  try {
    await api(`/api/notes/${openNote.id}`, { method: 'DELETE' });
    closeModal();
    refreshCurrentView();
  } catch (err) {
    setStatus(status, err.message, true);
  } finally {
    button.disabled = false;
  }
}

// ---------- 할 일 ----------
// 서버가 회의 날짜 오래된 순으로 준다. 기한은 자유 문구라 고치거나 정렬하지 않는다

async function loadTodos() {
  const status = document.querySelector('[data-role="todo-status"]');
  const tbody = document.getElementById('todoBody');
  try {
    const todos = await api('/api/todos');
    tbody.replaceChildren(...todos.map(buildTodoRow));
    setStatus(status, todos.length ? `할 일 ${todos.length}건 · 회의 날짜 오래된 순` : '모인 할 일이 없습니다.');
  } catch (err) {
    setStatus(status, err.message, true);
  }
}

function buildTodoRow(todo) {
  const row = el('tr', 'align-top even:bg-black/[0.02] dark:even:bg-white/[0.03]');
  row.appendChild(el('td', 'px-4 py-3 break-words', todo.what));
  row.appendChild(el('td', 'px-4 py-3 font-semibold', todo.who));
  row.appendChild(el('td', 'px-4 py-3', todo.when || '-'));
  const noteCell = el('td', 'px-4 py-3');
  const link = el('button', 'text-left text-sky-700 underline-offset-2 hover:underline dark:text-sky-400', todo.note_title);
  link.type = 'button';
  link.addEventListener('click', () => openModal(todo.note_id));
  noteCell.appendChild(link);
  row.appendChild(noteCell);
  return row;
}

// ---------- 탭 전환 ----------

const TAB_ACTIVE_CLASSES = ['bg-white', 'shadow-sm', 'dark:bg-neutral-700'];

let currentTab = 'list';

function showTab(tab) {
  currentTab = tab;
  document.querySelectorAll('[data-view]').forEach((view) => {
    view.classList.toggle('hidden', view.dataset.view !== tab);
  });
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    const active = btn.dataset.tab === tab;
    TAB_ACTIVE_CLASSES.forEach((cls) => btn.classList.toggle(cls, active));
    btn.setAttribute('aria-current', active ? 'page' : 'false');
  });
  // 다른 화면에서 바뀐 내용이 보이도록 화면에 들어올 때마다 다시 부른다
  refreshCurrentView();
}

// 상세 창에서 고치거나 지운 뒤, 지금 보고 있는 화면을 다시 부른다
function refreshCurrentView() {
  if (currentTab === 'todos') return loadTodos();
  if (currentTab === 'list') return loadNotes();
  return Promise.resolve(); // 넣기 화면은 다시 부를 것이 없다
}

// 지금 화면의 상태 문구 자리 (목록 또는 할 일)
function currentViewStatus() {
  const role = currentTab === 'todos' ? 'todo-status' : 'list-status';
  return document.querySelector(`[data-role="${role}"]`);
}

// ---------- 테마 ----------
// 초기값은 index.html 의 head 스크립트가 정한다 (저장값 > OS 설정)

const THEME_KEY = 'meetingnote-theme';

function toggleTheme() {
  const dark = document.documentElement.classList.toggle('dark');
  try {
    localStorage.setItem(THEME_KEY, dark ? 'dark' : 'light');
  } catch (err) {
    // 저장소를 못 쓰면 이번 방문 동안만 바뀐다
  }
}

// ---------- 시작 ----------

function init() {
  document.querySelector('[data-role="theme-toggle"]').addEventListener('click', toggleTheme);
  document.getElementById('metAt').value = nowForDateTimeLocal();
  document.getElementById('btnUp').addEventListener('click', uploadAudio);
  document.getElementById('btnSave').addEventListener('click', saveNote);
  const modal = document.getElementById('modal');
  // 창 안쪽이 아니라 바깥 어두운 영역을 눌렀을 때만 닫는다
  modal.addEventListener('click', (event) => { if (event.target === modal) closeModal(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && openNote) closeModal(); });
  modalPart('modal-close').addEventListener('click', closeModal);
  modalPart('modal-rename').addEventListener('click', renameNote);
  modalPart('modal-delete').addEventListener('click', deleteNote);
  // 검색은 입력할 때마다 다시 부른다
  ['q', 'from', 'to'].forEach((id) => {
    document.getElementById(id).addEventListener('input', loadNotes);
  });
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => showTab(btn.dataset.tab));
  });
  showTab(currentTab);
}

init();
