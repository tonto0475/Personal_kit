// PyCharm 2025.2 «Dark» 색 구성 → Monaco 테마 · 파이썬 토크나이저 · 파일 언어 판정
// 색 출처(설치본 원본): lib/app-client.jar themes/expUI/expUI_darkScheme.xml(Dark) · DefaultColorSchemesManager.xml(부모 Darcula)
//                       plugins/python-ce colorSchemes/PythonDarcula.xml(파이썬 전용). 유저 구성 _@user_Dark 는 북마크 색만 다름

export const PC = {
  bg: '#1e1f22', fg: '#bcbec4', caret: '#ced0d6', caretRow: '#26282e', lineNo: '#4b5059', lineNoCur: '#a1a3ab',
  sel: '#214283', indent: '#313438', indentCur: '#666870', margin: '#393b40', ws: '#6f737a',
  keyword: 'cf8e6d', string: '6aab73', number: '2aacb8', comment: '7a7e85', doc: '5f826b', todo: '8bb33d',
  func: '56a8f5', meta: 'b3ae60', builtin: '8888c6', self: '94558d', kwarg: 'aa4926', predefined: 'b200b2',
  bytes: 'a5c261', field: 'c77dbb', tag: 'd5b778', regexp: '42c3d4', text: 'bcbec4',
  added: '#549159', modified: '#375fad', deleted: '#868a91',
};

const PY_KW = ['and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else',
  'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass',
  'raise', 'return', 'try', 'while', 'with', 'yield', 'True', 'False', 'None'];
const PY_BUILTIN = ['abs', 'aiter', 'all', 'anext', 'any', 'ascii', 'bin', 'bool', 'breakpoint', 'bytearray', 'bytes',
  'callable', 'chr', 'classmethod', 'compile', 'complex', 'copyright', 'credits', 'delattr', 'dict', 'dir', 'divmod',
  'enumerate', 'eval', 'exec', 'exit', 'filter', 'float', 'format', 'frozenset', 'getattr', 'globals', 'hasattr', 'hash',
  'help', 'hex', 'id', 'input', 'int', 'isinstance', 'issubclass', 'iter', 'len', 'license', 'list', 'locals', 'map',
  'max', 'memoryview', 'min', 'next', 'object', 'oct', 'open', 'ord', 'pow', 'print', 'property', 'quit', 'range',
  'repr', 'reversed', 'round', 'set', 'setattr', 'slice', 'sorted', 'staticmethod', 'str', 'sum', 'super', 'tuple',
  'type', 'vars', 'zip', '__import__', 'NotImplemented', 'Ellipsis',
  'BaseException', 'BaseExceptionGroup', 'Exception', 'ExceptionGroup', 'ArithmeticError', 'AssertionError',
  'AttributeError', 'BlockingIOError', 'BrokenPipeError', 'BufferError', 'BytesWarning', 'ChildProcessError',
  'ConnectionAbortedError', 'ConnectionError', 'ConnectionRefusedError', 'ConnectionResetError', 'DeprecationWarning',
  'EOFError', 'EncodingWarning', 'EnvironmentError', 'FileExistsError', 'FileNotFoundError', 'FloatingPointError',
  'FutureWarning', 'GeneratorExit', 'IOError', 'ImportError', 'ImportWarning', 'IndentationError', 'IndexError',
  'InterruptedError', 'IsADirectoryError', 'KeyError', 'KeyboardInterrupt', 'LookupError', 'MemoryError',
  'ModuleNotFoundError', 'NameError', 'NotADirectoryError', 'NotImplementedError', 'OSError', 'OverflowError',
  'PendingDeprecationWarning', 'PermissionError', 'ProcessLookupError', 'RecursionError', 'ReferenceError',
  'ResourceWarning', 'RuntimeError', 'RuntimeWarning', 'StopAsyncIteration', 'StopIteration', 'SyntaxError',
  'SyntaxWarning', 'SystemError', 'SystemExit', 'TabError', 'TimeoutError', 'TypeError', 'UnboundLocalError',
  'UnicodeDecodeError', 'UnicodeEncodeError', 'UnicodeError', 'UnicodeTranslateError', 'UnicodeWarning',
  'UserWarning', 'ValueError', 'Warning', 'ZeroDivisionError'];

export const PY_LANG = 'python-pc';

// ======= 파이썬 토크나이저(Monarch) =======
// PyCharm 구분을 흉내: 키워드 · 내장 이름 · self/cls · def 이름 · __dunder__ · 데코레이터 · 키워드 인수 · 문서 문자열
//   · f-string 중괄호 · 바이트 문자열 · TODO 주석. 괄호 안(paren)에서만 «이름=» 을 키워드 인수로 칠함
function pythonDef() {
  const quoteRules = [];   // 문자열 시작 규칙(코드 상태용)
  const states = {};
  // 따옴표 4종 × 성격(plain · raw · f · rawf · bytes · rawbytes) 상태 생성
  const QUOTES = [['"""', 'tdq'], ["'''", 'tsq'], ['"', 'dq'], ["'", 'sq']];
  const KINDS = [
    { k: 'rb', pre: '(?:[rR][bB]|[bB][rR])', raw: true, f: false, tok: 'string.bytes' },
    { k: 'b', pre: '[bB]', raw: false, f: false, tok: 'string.bytes' },
    { k: 'rf', pre: '(?:[rR][fFtT]|[fFtT][rR])', raw: true, f: true, tok: 'string' },
    { k: 'f', pre: '[fFtT]', raw: false, f: true, tok: 'string' },
    { k: 'r', pre: '[rR]', raw: true, f: false, tok: 'string' },
    { k: 's', pre: '[uU]?', raw: false, f: false, tok: 'string' },
  ];
  const escQ = (q) => q.replace(/"/g, '\\"');
  for (const kind of KINDS) {
    for (const [q, qn] of QUOTES) {
      const name = `str_${kind.k}_${qn}`;
      const triple = q.length === 3;
      const qc = q[0];
      quoteRules.push([new RegExp(`${kind.pre}${escQ(q)}`), { token: kind.tok, next: `@${name}` }]);
      const rules = [];
      if (!kind.raw) {
        rules.push([/\\(?:[\\'"abfnrtv0]|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|N\{[^}]*\}|[0-7]{1,3})/, 'string.escape']);
      }
      rules.push([/\\$/, 'string.escape']);
      rules.push([/\\./, kind.tok]);
      if (kind.f) {
        rules.push([/\{\{|\}\}/, 'string.escape']);
        rules.push([/\{/, { token: 'fbrace', next: '@fexpr' }]);
      }
      rules.push([new RegExp(escQ(q)), { token: kind.tok, next: '@pop' }]);
      const body = `[^\\\\${kind.f ? '{}' : ''}${qc === '"' ? '"' : "'"}]`;
      if (triple) {
        rules.push([new RegExp(`${body}+`), kind.tok]);
        rules.push([new RegExp(qc === '"' ? '"' : "'"), kind.tok]);
      } else {
        // 한 줄 문자열이 줄 끝까지 안 닫히면 거기서 종료(뒤 코드가 전부 문자열 색이 되는 것 방지)
        rules.push([new RegExp(`${body}+$`), { token: kind.tok, next: '@pop' }]);
        rules.push([new RegExp(`${body}+`), kind.tok]);
      }
      if (kind.f) rules.push([/[{}]/, kind.tok]);
      states[name] = rules;
    }
  }
  // 문서 문자열(줄 첫머리의 삼중 따옴표)
  for (const [q, qn] of [['"""', 'dq'], ["'''", 'sq']]) {
    states[`doc_${qn}`] = [
      [/\\./, 'string.doc'],
      [new RegExp(escQ(q)), { token: 'string.doc', next: '@pop' }],
      [new RegExp(`[^\\\\${q[0] === '"' ? '"' : "'"}]+`), 'string.doc'],
      [new RegExp(q[0] === '"' ? '"' : "'"), 'string.doc'],
    ];
  }

  return {
    defaultToken: '',
    tokenPostfix: '.py',
    keywords: PY_KW,
    builtins: PY_BUILTIN,
    tokenizer: {
      root: [
        [/^(\s*)([rRuU]?)(""")/, ['white', 'string.doc', { token: 'string.doc', next: '@doc_dq' }]],
        [/^(\s*)([rRuU]?)(''')/, ['white', 'string.doc', { token: 'string.doc', next: '@doc_sq' }]],
        { include: '@code' },
      ],
      code: [
        [/\s+/, 'white'],
        [/#\s*(?:TODO|FIXME|XXX)\b.*$/, 'comment.todo'],
        [/#.*$/, 'comment'],
        ...quoteRules,
        [/@[A-Za-z_][\w.]*/, 'decorator'],
        [/(def)(\s+)(__\w+__)/, ['keyword', 'white', { token: 'predefined.def', next: '@sig' }]],
        [/(def)(\s+)([A-Za-z_]\w*)/, ['keyword', 'white', { token: 'function.def', next: '@sig' }]],
        [/(class)(\s+)([A-Za-z_]\w*)/, ['keyword', 'white', 'class.def']],
        [/(match|case)(?=\s+[^\s=:.,)\]}].*:\s*(?:#.*)?$)/, 'keyword'],
        [/0[xX][0-9a-fA-F_]+/, 'number.hex'],
        [/0[oO][0-7_]+/, 'number.octal'],
        [/0[bB][01_]+/, 'number.binary'],
        [/(?:\d[\d_]*)?\.\d[\d_]*(?:[eE][+-]?\d[\d_]*)?[jJ]?/, 'number.float'],
        [/\d[\d_]*\.(?:[eE][+-]?\d[\d_]*)?[jJ]?/, 'number.float'],
        [/\d[\d_]*[eE][+-]?\d[\d_]*[jJ]?/, 'number.float'],
        [/\d[\d_]*[jJ]?/, 'number'],
        [/(\.)(\s*)([A-Za-z_]\w*)/, ['delimiter', 'white', { cases: { '~__\\w+__': 'predefined', '@default': 'identifier' } }]],
        [/[A-Za-z_]\w*/, { cases: { '@keywords': 'keyword', 'self': 'self', 'cls': 'self', '@builtins': 'builtin',
          '~__\\w+__': 'predefined', '@default': 'identifier' } }],
        [/\(/, { token: 'delimiter.parenthesis', next: '@paren' }],
        [/\[/, { token: 'delimiter.bracket', next: '@brack' }],
        [/\{/, { token: 'delimiter.curly', next: '@brace' }],
        [/[)\]}]/, 'delimiter'],
        [/->|[-+*/%@&|^~<>!=:]=?|\*\*=?|\/\/=?|<<=?|>>=?/, 'operator'],
        [/[,;.\\]/, 'delimiter'],
      ],
      // 괄호 속에서 줄 첫머리가 문장 시작 키워드면 닫는 괄호를 잃은 것으로 보고 처음으로(미완성 코드 대비)
      reset: [
        [/^(?=\s*(?:(?:def|class|return|import|from|raise|try|except|finally|while|with|elif|async\s+def)\b|@))/, { token: '', next: '@popall' }],
      ],
      paren: [
        { include: '@reset' },
        [/([A-Za-z_]\w*)(\s*)(=)(?!=)/, ['kwarg', 'white', 'operator']],
        [/\)/, { token: 'delimiter.parenthesis', next: '@pop' }],
        { include: '@code' },
      ],
      brack: [
        { include: '@reset' },
        [/\]/, { token: 'delimiter.bracket', next: '@pop' }],
        { include: '@code' },
      ],
      brace: [
        { include: '@reset' },
        [/\}/, { token: 'delimiter.curly', next: '@pop' }],
        { include: '@code' },
      ],
      // def 머리: 이름 뒤 (매개변수) [-> 반환형] :
      sig: [
        [/\(/, { token: 'delimiter.parenthesis', next: '@sigParen' }],
        [/:/, { token: 'delimiter', next: '@pop' }],
        { include: '@code' },
      ],
      sigParen: [
        [/\b(?:self|cls)\b/, 'self'],
        [/\)/, { token: 'delimiter.parenthesis', next: '@pop' }],
        [/\(/, { token: 'delimiter.parenthesis', next: '@sigParen' }],
        { include: '@code' },
      ],
      // f-string 안 식 { … } · 서식 지정 { …:>10 }
      fexpr: [
        [/\}/, { token: 'fbrace', next: '@pop' }],
        [/![rsa](?=[:}])/, 'string.escape'],
        [/:(?=[^}]*\})/, { token: 'string', next: '@fspec' }],
        { include: '@code' },
      ],
      fspec: [
        [/(?=\})/, { token: '', next: '@pop' }],
        [/\{/, { token: 'fbrace', next: '@fexpr' }],
        [/[^{}]+/, 'string'],
      ],
      ...states,
    },
  };
}

function pythonConf(monaco) {
  const { IndentAction } = monaco.languages;
  return {
    comments: { lineComment: '#', blockComment: ['"""', '"""'] },
    brackets: [['{', '}'], ['[', ']'], ['(', ')']],
    autoClosingPairs: [
      { open: '{', close: '}' }, { open: '[', close: ']' }, { open: '(', close: ')' },
      { open: '"', close: '"', notIn: ['string'] }, { open: "'", close: "'", notIn: ['string', 'comment'] },
    ],
    surroundingPairs: [
      { open: '{', close: '}' }, { open: '[', close: ']' }, { open: '(', close: ')' },
      { open: '"', close: '"' }, { open: "'", close: "'" },
    ],
    // PyCharm 처럼: «:» 로 끝난 줄 다음은 한 단계 들여쓰기, return · pass · break · continue · raise 다음은 한 단계 내어쓰기
    onEnterRules: [
      { beforeText: /^\s*[^#\s].*:\s*(?:#.*)?$/, action: { indentAction: IndentAction.Indent } },
      { beforeText: /^\s*(?:pass|break|continue)\s*(?:#.*)?$/, action: { indentAction: IndentAction.Outdent } },
      { beforeText: /^\s*(?:return|raise)\b(?!.*[([{,\\]\s*(?:#.*)?$).*$/, action: { indentAction: IndentAction.Outdent } },
    ],
    indentationRules: {
      increaseIndentPattern: /^\s*[^#\s].*:\s*(?:#.*)?$/,
      decreaseIndentPattern: /^\s*(?:else|elif\b.*|except\b.*|finally)\s*:\s*(?:#.*)?$/,
    },
    folding: { offSide: true, markers: { start: /^\s*#\s*region\b/, end: /^\s*#\s*endregion\b/ } },
  };
}

// ======= 테마 =======
function defineTheme(monaco) {
  const r = (token, foreground, fontStyle) => ({ token, foreground, ...(fontStyle ? { fontStyle } : {}) });
  const rules = [
    r('', PC.text), r('white', PC.text), r('identifier', PC.text), r('delimiter', PC.text), r('operator', PC.text),
    r('keyword', PC.keyword), r('string', PC.string), r('string.escape', PC.keyword), r('string.doc', PC.doc, 'italic'),
    r('string.bytes', PC.bytes), r('number', PC.number), r('comment', PC.comment), r('comment.doc', PC.doc, 'italic'),
    r('comment.todo', PC.todo, 'italic'), r('regexp', PC.regexp), r('decorator', PC.meta), r('annotation', PC.meta),
    r('function.def', PC.func), r('predefined', PC.predefined), r('class.def', PC.text), r('builtin', PC.builtin),
    r('self', PC.self), r('kwarg', PC.kwarg), r('fbrace', PC.keyword), r('type', PC.text), r('type.identifier', PC.text),
    r('tag', PC.tag), r('metatag', PC.tag), r('attribute.name', PC.text), r('attribute.value', PC.string),
    r('string.key.json', PC.field), r('string.value.json', PC.string), r('keyword.json', PC.keyword),
    r('type.yaml', PC.keyword), r('attribute.name.css', PC.field), r('variable', PC.field), r('variable.predefined', PC.field),
    r('key', PC.keyword), r('constant', PC.field), r('predefined.sql', PC.builtin), r('invalid', 'f75464'),
  ];
  monaco.editor.defineTheme('pycharm-dark', {
    base: 'vs-dark',
    inherit: true,
    rules,
    colors: {
      'editor.background': PC.bg, 'editor.foreground': '#' + PC.text,
      'editorLineNumber.foreground': PC.lineNo, 'editorLineNumber.activeForeground': PC.lineNoCur,
      'editorCursor.foreground': PC.caret, 'editor.lineHighlightBackground': PC.caretRow, 'editor.lineHighlightBorder': '#00000000',
      'editor.selectionBackground': PC.sel, 'editor.inactiveSelectionBackground': '#214283aa',
      'editor.selectionHighlightBackground': '#373b39', 'editor.wordHighlightBackground': '#373b39',
      'editor.wordHighlightStrongBackground': '#402f33', 'editor.findMatchBackground': '#114957',
      'editor.findMatchHighlightBackground': '#2d543f', 'editor.findMatchBorder': '#72d6d6',
      'editorBracketMatch.background': '#43454a', 'editorBracketMatch.border': '#00000000',
      'editorIndentGuide.background1': PC.indent, 'editorIndentGuide.activeBackground1': PC.indentCur,
      'editorRuler.foreground': PC.margin, 'editorWhitespace.foreground': PC.ws, 'editorGutter.background': PC.bg,
      'editorGutter.addedBackground': PC.added, 'editorGutter.modifiedBackground': PC.modified,
      'editorGutter.deletedBackground': PC.deleted, 'editorGutter.foldingControlForeground': '#868a91',
      'editorWidget.background': '#2b2d30', 'editorWidget.border': '#43454a', 'editorWidget.foreground': '#dfe1e5',
      'editorSuggestWidget.background': '#2b2d30', 'editorSuggestWidget.border': '#43454a',
      'editorSuggestWidget.selectedBackground': '#2e436e', 'editorSuggestWidget.highlightForeground': '#548af7',
      'editorHoverWidget.background': '#2b2d30', 'editorHoverWidget.border': '#43454a',
      'input.background': '#1e1f22', 'input.border': '#4e5157', 'input.foreground': '#dfe1e5', 'focusBorder': '#3574f0',
      'inputOption.activeBorder': '#3574f0', 'inputOption.activeBackground': '#2e436e',
      'list.activeSelectionBackground': '#2e436e', 'list.inactiveSelectionBackground': '#43454a',
      'list.hoverBackground': '#393b40', 'list.highlightForeground': '#548af7', 'list.focusOutline': '#00000000',
      'quickInput.background': '#2b2d30', 'quickInputList.focusBackground': '#2e436e', 'pickerGroup.foreground': '#868a91',
      'scrollbarSlider.background': '#4e515766', 'scrollbarSlider.hoverBackground': '#5a5d6399',
      'scrollbarSlider.activeBackground': '#6f737acc', 'scrollbar.shadow': '#00000000',
      'editorOverviewRuler.border': '#00000000', 'editorStickyScroll.background': PC.bg,
      'editorStickyScrollHover.background': '#2b2d30', 'editorStickyScroll.shadow': '#00000066',
      'diffEditor.insertedLineBackground': '#294436', 'diffEditor.insertedTextBackground': '#3b6b4c',
      'diffEditor.removedLineBackground': '#484a4a', 'diffEditor.removedTextBackground': '#6a6d6e',
      'diffEditorGutter.insertedLineBackground': '#294436', 'diffEditorGutter.removedLineBackground': '#484a4a',
      'diffEditorOverview.insertedForeground': '#549159', 'diffEditorOverview.removedForeground': '#868a91',
      'diffEditor.diagonalFill': '#2b2d30', 'diffEditor.unchangedRegionBackground': '#2b2d30',
      'diffEditor.unchangedRegionForeground': '#868a91', 'diffEditor.unchangedCodeBackground': '#26282e80',
      'diffEditor.move.border': '#56a8f5',
      'menu.background': '#2b2d30', 'menu.foreground': '#dfe1e5', 'menu.selectionBackground': '#2e436e',
      'menu.separatorBackground': '#43454a', 'menu.border': '#43454a',
    },
  });
}

// ======= 파일 → 언어 =======
const LANG = {
  py: PY_LANG, pyw: PY_LANG, pyi: PY_LANG, js: 'javascript', mjs: 'javascript', cjs: 'javascript', jsx: 'javascript',
  ts: 'typescript', tsx: 'typescript', mts: 'typescript', json: 'json', jsonc: 'json', ipynb: 'json', webmanifest: 'json',
  html: 'html', htm: 'html', css: 'css', scss: 'scss', less: 'less', yml: 'yaml', yaml: 'yaml', toml: 'ini', ini: 'ini',
  cfg: 'ini', conf: 'ini', properties: 'ini', sh: 'shell', bash: 'shell', zsh: 'shell', sql: 'sql', xml: 'xml',
  svg: 'xml', go: 'go', java: 'java', kt: 'kotlin', rs: 'rust', c: 'c', h: 'cpp', cpp: 'cpp', hpp: 'cpp', cs: 'csharp',
  rb: 'ruby', php: 'php', lua: 'lua', r: 'r', swift: 'swift', ps1: 'powershell', bat: 'bat', cmd: 'bat',
  graphql: 'graphql', gql: 'graphql', proto: 'protobuf', dockerfile: 'dockerfile', md: 'markdown', markdown: 'markdown',
};
export function langOf(path) {
  const name = (path || '').split('/').pop().toLowerCase();
  if (name === 'dockerfile' || name.startsWith('dockerfile.')) return 'dockerfile';
  if (name.startsWith('.env') || name === '.gitignore' || name === '.dockerignore' || name === '.editorconfig') return 'ini';
  if (['.bashrc', '.profile', '.bash_profile', '.zshrc'].includes(name)) return 'shell';
  const ext = name.includes('.') ? name.split('.').pop() : '';
  return LANG[ext] || 'plaintext';
}
export const LANG_LABEL = {
  [PY_LANG]: 'Python', javascript: 'JavaScript', typescript: 'TypeScript', json: 'JSON', html: 'HTML', css: 'CSS',
  scss: 'SCSS', yaml: 'YAML', ini: 'INI', shell: 'Shell', sql: 'SQL', xml: 'XML', markdown: 'Markdown',
  plaintext: '텍스트', dockerfile: 'Dockerfile',
};

export function setupMonaco(monaco) {
  monaco.languages.register({ id: PY_LANG, extensions: ['.py', '.pyw', '.pyi'], aliases: ['Python', 'python'] });
  monaco.languages.setMonarchTokensProvider(PY_LANG, pythonDef());
  monaco.languages.setLanguageConfiguration(PY_LANG, pythonConf(monaco));
  defineTheme(monaco);
  // JS · TS: 모듈을 못 찾는 등 의미 검사는 끔(문법 오류만) — 의존성이 없는 작업 폴더에서 빨간 줄 남발 방지
  const ts = monaco.languages.typescript;
  if (ts) {
    for (const d of [ts.javascriptDefaults, ts.typescriptDefaults]) {
      d.setDiagnosticsOptions({ noSemanticValidation: true, noSyntaxValidation: false });
    }
  }
}
