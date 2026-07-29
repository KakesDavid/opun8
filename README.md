<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Opun8 — Deploy anywhere. Type once.</title>
<meta name="description" content="Opun8 is a universal deployment CLI for Vercel, Netlify, Render, and GitHub. One command, zero friction.">

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">

<style>
  /* ============================================================
     TOKENS
  ============================================================ */
  :root{
    --ink:        #0b0a08;
    --ink-raised: #141210;
    --ink-line:   rgba(246,243,234,0.09);
    --paper:      #f6f3ea;
    --paper-dim:  #a39c8c;
    --gold:       #d3a949;
    --gold-bright:#f2ca6e;
    --gold-line:  rgba(211,169,73,0.30);
    --gold-wash:  rgba(211,169,73,0.07);
    --green:      #86b06e;

    --font-display:'Fraunces', Georgia, 'Times New Roman', serif;
    --font-mono:   'JetBrains Mono', ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace;
    --font-body:   'Inter', -apple-system, BlinkMacSystemFont, sans-serif;

    --container: 1140px;
    --container-narrow: 760px;
    --radius: 3px;
    --section-pad: clamp(64px, 9vw, 120px);
  }

  *,*::before,*::after{ box-sizing:border-box; margin:0; padding:0; }
  html{ scroll-behavior:smooth; }

  body{
    background:var(--ink);
    color:var(--paper);
    font-family:var(--font-body);
    font-size:16px;
    line-height:1.6;
    -webkit-font-smoothing:antialiased;
    overflow-x:hidden;
  }

  img,svg{ display:block; max-width:100%; }
  a{ color:inherit; text-decoration:none; }
  ul,ol{ list-style:none; }

  ::selection{ background:var(--gold); color:var(--ink); }

  :focus-visible{
    outline:2px solid var(--gold-bright);
    outline-offset:3px;
  }

  @media (prefers-reduced-motion: reduce){
    *{
      animation-duration:0.001ms !important;
      animation-iteration-count:1 !important;
      transition-duration:0.001ms !important;
      scroll-behavior:auto !important;
    }
  }

  .container{ max-width:var(--container); margin:0 auto; padding:0 28px; }
  .container--narrow{ max-width:var(--container-narrow); }

  .gold-text{ color:var(--gold); }

  /* ============================================================
     REVEAL ON SCROLL
  ============================================================ */
  .reveal{
    opacity:0;
    transform:translateY(16px);
    transition:opacity .6s ease, transform .6s ease;
  }
  .reveal.is-visible{ opacity:1; transform:translateY(0); }

  /* ============================================================
     NAV
  ============================================================ */
  .nav{
    position:sticky; top:0; z-index:50;
    background:rgba(11,10,8,0.82);
    backdrop-filter:blur(10px);
    border-bottom:1px solid var(--ink-line);
  }
  .nav__inner{
    display:flex; align-items:center; justify-content:space-between;
    height:64px;
  }
  .nav__brand{
    display:flex; align-items:center; gap:10px;
    font-family:var(--font-display); font-weight:600; font-size:1.15rem;
    letter-spacing:.01em;
  }
  .nav__brand span{ color:var(--paper); }
  .nav__links{ display:flex; gap:28px; }
  .nav__links a{
    font-size:.9rem; color:var(--paper-dim);
    transition:color .2s ease;
  }
  .nav__links a:hover{ color:var(--gold-bright); }
  .nav__star{
    font-family:var(--font-mono); font-size:.82rem;
    border:1px solid var(--gold-line);
    padding:8px 14px; border-radius:var(--radius);
    color:var(--gold);
    transition:background .2s ease, color .2s ease, border-color .2s ease;
    white-space:nowrap;
  }
  .nav__star:hover{ background:var(--gold); color:var(--ink); border-color:var(--gold); }
  .nav__mobile-hide{ display:flex; }
  @media (max-width:760px){
    .nav__links{ display:none; }
  }

  /* ============================================================
     SECTION SCAFFOLDING
  ============================================================ */
  .section{ padding:var(--section-pad) 0; }
  .section--raised{ background:var(--ink-raised); border-top:1px solid var(--ink-line); border-bottom:1px solid var(--ink-line); }

  .section__eyebrow{
    font-family:var(--font-mono); font-size:.78rem;
    letter-spacing:.14em; text-transform:uppercase;
    color:var(--gold); margin-bottom:14px;
  }
  .section__eyebrow::before{ content:'// '; color:var(--gold-line); }
  .section__title{
    font-family:var(--font-display); font-weight:600;
    font-size:clamp(1.7rem, 3.4vw, 2.5rem);
    line-height:1.2; max-width:26ch;
    margin-bottom:18px;
  }
  .section__lead{
    color:var(--paper-dim); max-width:60ch; font-size:1.02rem;
    margin-bottom:40px;
  }

  /* ============================================================
     BUTTONS
  ============================================================ */
  .btn{
    display:inline-flex; align-items:center; gap:10px;
    font-family:var(--font-mono); font-size:.92rem;
    padding:13px 20px; border-radius:var(--radius);
    cursor:pointer; border:1px solid transparent;
    transition:transform .15s ease, background .2s ease, border-color .2s ease, color .2s ease;
  }
  .btn:active{ transform:translateY(1px); }
  .btn--primary{
    background:var(--gold); color:var(--ink); font-weight:600;
    border-color:var(--gold);
  }
  .btn--primary:hover{ background:var(--gold-bright); border-color:var(--gold-bright); }
  .btn--primary .btn__prompt{ opacity:.6; }
  .btn--primary .btn__copy-label{
    margin-left:auto; padding-left:14px; font-size:.72rem;
    opacity:.55; text-transform:uppercase; letter-spacing:.08em;
  }
  .btn--primary.copied{ background:var(--green); border-color:var(--green); color:var(--ink); }
  .btn--ghost{
    color:var(--paper); border-color:var(--ink-line);
  }
  .btn--ghost:hover{ border-color:var(--gold-line); color:var(--gold-bright); }

  /* ============================================================
     HERO
  ============================================================ */
  .hero{
    position:relative;
    padding:88px 0 var(--section-pad);
    overflow:hidden;
  }
  .hero::before{
    content:'';
    position:absolute; inset:0;
    background:
      radial-gradient(ellipse 900px 500px at 15% -10%, var(--gold-wash), transparent 60%),
      repeating-linear-gradient(180deg, rgba(246,243,234,0.015) 0px, rgba(246,243,234,0.015) 1px, transparent 1px, transparent 3px);
    pointer-events:none;
  }
  .hero__inner{
    position:relative; z-index:1;
    display:grid; grid-template-columns:1.05fr 1fr; gap:56px; align-items:center;
  }
  .eyebrow{
    font-family:var(--font-mono); font-size:.8rem; letter-spacing:.14em;
    text-transform:uppercase; color:var(--gold); margin-bottom:22px;
  }
  .hero__copy h1{
    font-family:var(--font-display); font-weight:600;
    font-size:clamp(2.4rem, 5.2vw, 3.8rem);
    line-height:1.08; letter-spacing:-.01em;
    margin-bottom:22px;
  }
  .hero__sub{
    color:var(--paper-dim); font-size:1.08rem; max-width:46ch;
    margin-bottom:34px;
  }
  .hero__cta{ display:flex; flex-wrap:wrap; gap:14px; margin-bottom:34px; }
  .hero__badges{ display:flex; flex-wrap:wrap; gap:10px; }
  .hero__badges li{
    font-family:var(--font-mono); font-size:.76rem; color:var(--paper-dim);
    border:1px solid var(--ink-line); padding:6px 11px; border-radius:20px;
  }

  /* Terminal component — the signature element, reused across the page */
  .terminal{
    background:var(--ink-raised);
    border:1px solid var(--gold-line);
    border-radius:6px;
    overflow:hidden;
    box-shadow:0 30px 70px -30px rgba(0,0,0,0.7), 0 0 0 1px rgba(0,0,0,0.4);
  }
  .terminal__bar{
    display:flex; align-items:center; gap:8px;
    padding:11px 16px;
    background:linear-gradient(180deg, rgba(246,243,234,0.04), transparent);
    border-bottom:1px solid var(--ink-line);
  }
  .terminal__dot{
    width:9px; height:9px; border-radius:50%;
    background:var(--gold-line);
    border:1px solid var(--gold-line);
  }
  .terminal__title{
    font-family:var(--font-mono); font-size:.74rem; color:var(--paper-dim);
    margin-left:6px;
  }
  .terminal__body{
    font-family:var(--font-mono); font-size:.86rem; line-height:1.75;
    padding:22px 22px 26px;
    min-height:260px;
    white-space:pre-wrap;
  }
  .terminal--wide .terminal__body{ min-height:0; }
  .t-line{ display:block; }
  .t-prompt{ color:var(--gold); margin-right:8px; }
  .t-out{ color:var(--paper-dim); }
  .t-gold{ color:var(--gold-bright); }
  .t-cursor{
    display:inline-block; width:7px; height:1em; background:var(--gold-bright);
    vertical-align:text-bottom; margin-left:2px;
    animation:blink 1s steps(1) infinite;
  }
  @keyframes blink{ 50%{ opacity:0; } }

  @media (max-width:900px){
    .hero__inner{ grid-template-columns:1fr; }
  }

  /* ============================================================
     FEATURE GRID
  ============================================================ */
  .grid{ display:grid; gap:20px; }
  .grid--features{ grid-template-columns:repeat(4, 1fr); }
  .feature{
    position:relative;
    padding:26px 22px;
    border:1px solid var(--ink-line);
    border-radius:var(--radius);
    transition:border-color .2s ease, transform .2s ease;
  }
  .feature:hover{ border-color:var(--gold-line); transform:translateY(-3px); }
  .feature::before, .feature::after{
    content:''; position:absolute; width:10px; height:10px;
    border-color:var(--gold-line); border-style:solid; opacity:0; transition:opacity .2s ease;
  }
  .feature::before{ top:-1px; left:-1px; border-width:1px 0 0 1px; }
  .feature::after{ bottom:-1px; right:-1px; border-width:0 1px 1px 0; }
  .feature:hover::before, .feature:hover::after{ opacity:1; }
  .feature__icon{ font-size:1.3rem; margin-bottom:14px; }
  .feature__title{ font-weight:600; font-size:1rem; margin-bottom:8px; }
  .feature__desc{ color:var(--paper-dim); font-size:.9rem; line-height:1.55; }

  @media (max-width:900px){ .grid--features{ grid-template-columns:repeat(2, 1fr); } }
  @media (max-width:560px){ .grid--features{ grid-template-columns:1fr; } }

  /* ============================================================
     QUICK START — genuine sequence, numbered
  ============================================================ */
  .steps{
    position:relative;
    display:flex; flex-direction:column; gap:36px;
    padding-left:56px;
  }
  .steps::before{
    content:'';
    position:absolute; left:19px; top:8px; bottom:8px; width:1px;
    background:var(--gold-line);
  }
  .step{ position:relative; }
  .step__num{
    position:absolute; left:-56px; top:0;
    width:40px; height:40px; border-radius:50%;
    background:var(--ink); border:1px solid var(--gold-line);
    display:flex; align-items:center; justify-content:center;
    font-family:var(--font-mono); font-size:.85rem; color:var(--gold);
  }
  .step__title{ font-weight:600; font-size:1.05rem; margin-bottom:6px; }
  .step__desc{ color:var(--paper-dim); font-size:.92rem; margin-bottom:14px; }
  .step__term{
    background:var(--ink);
    border:1px solid var(--ink-line);
    border-radius:var(--radius);
    padding:14px 18px;
    font-family:var(--font-mono); font-size:.84rem; line-height:1.8;
  }
  .step__term .t-prompt{ margin-right:8px; }

  /* ============================================================
     ENV VARS DEMO
  ============================================================ */
  .envrow{ display:flex; align-items:baseline; gap:12px; }
  .envrow .chk{ color:var(--gold); width:26px; flex:none; }
  .envrow .chk--off{ color:var(--paper-dim); }
  .envrow .name{ color:var(--paper); width:150px; flex:none; }
  .envrow .loc{ color:var(--paper-dim); font-size:.8rem; }
  .env-divider{ height:1px; background:var(--ink-line); margin:16px 0; }
  .env-cmdlist{ color:var(--paper-dim); }
  .env-cmdlist b{ color:var(--paper); font-weight:600; }
  .masked{ letter-spacing:.2em; }

  /* ============================================================
     PROVIDERS
  ============================================================ */
  .grid--providers{ grid-template-columns:repeat(4, 1fr); }
  .provider{
    border-left:2px solid var(--gold-line);
    padding:4px 0 4px 22px;
  }
  .provider__head{ display:flex; align-items:center; gap:10px; margin-bottom:14px; }
  .provider__title{ font-family:var(--font-display); font-weight:600; font-size:1.15rem; }
  .provider__tag{
    font-family:var(--font-mono); font-size:.66rem; letter-spacing:.06em;
    color:var(--ink); background:var(--gold); padding:2px 7px; border-radius:20px;
  }
  .provider li{
    color:var(--paper-dim); font-size:.88rem; line-height:2;
    display:flex; gap:8px;
  }
  .provider li .ck{ color:var(--green); flex:none; }

  @media (max-width:960px){ .grid--providers{ grid-template-columns:repeat(2, 1fr); } }
  @media (max-width:560px){ .grid--providers{ grid-template-columns:1fr; } }

  /* ============================================================
     COST ESTIMATOR
  ============================================================ */
  .grid--cost{ grid-template-columns:1fr 1fr; }
  .cost-row{
    display:flex; justify-content:space-between; align-items:baseline;
    padding:9px 0; font-size:.87rem;
  }
  .cost-row .lbl{ color:var(--paper-dim); }
  .cost-row .val{ font-family:var(--font-mono); color:var(--paper); }
  .cost-row--total .val{ color:var(--gold-bright); font-weight:600; font-size:1.05rem; }
  .cost-divider{ height:1px; background:var(--ink-line); margin:6px 0; }
  .cost-meta{ color:var(--paper-dim); font-size:.78rem; margin-bottom:6px; }
  .cost-bar{ height:6px; border-radius:3px; background:var(--ink-line); overflow:hidden; margin-top:14px; }
  .cost-bar__fill{ height:100%; background:var(--gold); border-radius:3px; }
  .cost-note{ font-family:var(--font-mono); font-size:.76rem; color:var(--paper-dim); margin-top:8px; }

  @media (max-width:760px){ .grid--cost{ grid-template-columns:1fr; } }

  /* ============================================================
     COMMANDS
  ============================================================ */
  .commands{ display:grid; grid-template-columns:repeat(2, 1fr); gap:44px 56px; }
  .cmd-group__title{
    font-family:var(--font-mono); font-size:.76rem; letter-spacing:.1em;
    text-transform:uppercase; color:var(--gold); margin-bottom:16px;
    padding-bottom:10px; border-bottom:1px solid var(--ink-line);
  }
  .cmd-row{
    display:flex; gap:18px; padding:9px 0;
    border-bottom:1px solid var(--ink-line);
    transition:padding-left .15s ease, border-color .15s ease;
  }
  .cmd-row:last-child{ border-bottom:none; }
  .cmd-row:hover{ padding-left:6px; border-color:var(--gold-line); }
  .cmd-row code{
    font-family:var(--font-mono); font-size:.85rem; color:var(--paper);
    flex:none; width:200px;
  }
  .cmd-row span{ color:var(--paper-dim); font-size:.85rem; }

  @media (max-width:760px){
    .commands{ grid-template-columns:1fr; }
    .cmd-row code{ width:160px; }
  }

  /* ============================================================
     BADGES LADDER
  ============================================================ */
  .ladder{
    display:flex; gap:18px; overflow-x:auto; padding-bottom:12px;
    scroll-snap-type:x proximity;
  }
  .medal{
    scroll-snap-align:start;
    flex:none; width:168px;
    border:1px solid var(--ink-line);
    border-radius:var(--radius);
    padding:22px 18px;
    text-align:center;
    transition:border-color .2s ease, transform .2s ease;
  }
  .medal:hover{ border-color:var(--gold-line); transform:translateY(-4px); }
  .medal__ring{
    width:56px; height:56px; margin:0 auto 14px;
    border-radius:50%; border:1px solid var(--gold-line);
    display:flex; align-items:center; justify-content:center;
    font-size:1.5rem;
    background:radial-gradient(circle, var(--gold-wash), transparent 70%);
  }
  .medal__lvl{ font-family:var(--font-mono); font-size:.7rem; color:var(--gold); margin-bottom:6px; }
  .medal__name{ font-weight:600; font-size:.92rem; margin-bottom:4px; }
  .medal__req{ font-family:var(--font-mono); font-size:.76rem; color:var(--paper-dim); }

  /* ============================================================
     DEVELOP / CONTRIBUTE
  ============================================================ */
  .grid--split{ grid-template-columns:1fr 1fr; gap:60px; }
  .dev-term{
    background:var(--ink); border:1px solid var(--ink-line); border-radius:var(--radius);
    padding:18px 20px; font-family:var(--font-mono); font-size:.83rem; line-height:2;
  }
  .dev-term .t-out{ display:block; margin-bottom:8px; }
  .contrib-list{ display:flex; flex-direction:column; gap:10px; margin-bottom:26px; }
  .contrib-list li{
    display:flex; gap:12px; font-family:var(--font-mono); font-size:.85rem; color:var(--paper-dim);
  }
  .contrib-list li b{ color:var(--gold); font-weight:600; }
  .help-areas{ display:flex; flex-wrap:wrap; gap:8px; }
  .help-areas li{
    font-size:.8rem; color:var(--paper-dim);
    border:1px solid var(--ink-line); border-radius:20px; padding:6px 12px;
  }

  @media (max-width:800px){ .grid--split{ grid-template-columns:1fr; gap:48px; } }

  /* ============================================================
     FOOTER
  ============================================================ */
  .footer{ padding:64px 0 40px; border-top:1px solid var(--ink-line); }
  .footer__inner{ text-align:center; }
  .footer__brand{
    font-family:var(--font-display); font-weight:600; font-size:1.4rem;
    margin-bottom:10px;
  }
  .footer__tag{ color:var(--paper-dim); font-size:.92rem; margin-bottom:26px; }
  .footer__cta{ margin-bottom:30px; }
  .footer__meta{
    font-family:var(--font-mono); font-size:.76rem; color:var(--paper-dim);
    display:flex; justify-content:center; gap:18px; flex-wrap:wrap;
  }
  .footer__meta a:hover{ color:var(--gold-bright); }
</style>
</head>
<body>

  <!-- ============================================================ NAV -->
  <header class="nav">
    <div class="nav__inner container">
      <a class="nav__brand" href="#top">🦉<span>Opun8</span></a>
      <nav class="nav__links">
        <a href="https://opun8.dev/docs">Docs</a>
        <a href="https://github.com/KakesDavid/opun8/issues">Report bug</a>
        <a href="https://github.com/KakesDavid/opun8">GitHub</a>
      </nav>
      <a class="nav__star" href="https://github.com/KakesDavid/opun8/stargazers">★ Star on GitHub</a>
    </div>
  </header>

  <!-- ============================================================ HERO -->
  <section class="hero" id="top">
    <div class="hero__inner container">
      <div class="hero__copy reveal">
        <p class="eyebrow">Universal deployment CLI</p>
        <h1>Deploy anywhere.<br><span class="gold-text">Type once.</span></h1>
        <p class="hero__sub">One command reaches Vercel, Netlify, Render, and GitHub. Opun8 detects your project, asks what it needs to know, and ships it — no DevOps degree required.</p>
        <div class="hero__cta">
          <button class="btn btn--primary" data-copy="pip install opun8" aria-label="Copy install command">
            <span class="btn__prompt">$</span> pip install opun8
            <span class="btn__copy-label">copy</span>
          </button>
          <a class="btn btn--ghost" href="https://github.com/KakesDavid/opun8">View on GitHub</a>
        </div>
        <ul class="hero__badges">
          <li>PyPI · v0.1.5</li>
          <li>Python 3.8+</li>
          <li>MIT License</li>
          <li>Windows · macOS · Linux · Termux</li>
        </ul>
      </div>

      <div class="hero__terminal reveal">
        <div class="terminal">
          <div class="terminal__bar">
            <span class="terminal__dot"></span>
            <span class="terminal__title">opun8 — zsh</span>
          </div>
          <div class="terminal__body" id="hero-terminal" aria-hidden="true"></div>
        </div>
      </div>
    </div>
  </section>

  <!-- ============================================================ WHY -->
  <section class="section" id="why">
    <div class="container">
      <p class="section__eyebrow">Why Opun8</p>
      <h2 class="section__title">Every provider, one vocabulary.</h2>
      <p class="section__lead">Stop relearning a new dashboard for every host. Opun8 brings Vercel, Render, Netlify, and GitHub into a single, unified CLI experience.</p>

      <div class="grid grid--features">
        <div class="feature">
          <div class="feature__icon">🚀</div>
          <div class="feature__title">One command</div>
          <div class="feature__desc">Deploy with <code>opun8 deploy vercel</code>, <code>netlify</code>, or <code>render</code> — same shape every time.</div>
        </div>
        <div class="feature">
          <div class="feature__icon">🧠</div>
          <div class="feature__title">Smart detection</div>
          <div class="feature__desc">Auto-detects React, Next.js, Vue, Node.js, Python, and static HTML projects.</div>
        </div>
        <div class="feature">
          <div class="feature__icon">🔐</div>
          <div class="feature__title">Secure auth</div>
          <div class="feature__desc">OAuth 2.0 + PKCE by default, with personal access token fallback for CI.</div>
        </div>
        <div class="feature">
          <div class="feature__icon">💰</div>
          <div class="feature__title">Cost estimator</div>
          <div class="feature__desc">See what a deployment will cost before you commit to it.</div>
        </div>
        <div class="feature">
          <div class="feature__icon">📱</div>
          <div class="feature__title">Works anywhere</div>
          <div class="feature__desc">Windows, macOS, Linux, and Termux on Android — same binary, same commands.</div>
        </div>
        <div class="feature">
          <div class="feature__icon">🏅</div>
          <div class="feature__title">History &amp; badges</div>
          <div class="feature__desc">Every deployment is logged. Ship enough of them and you'll earn it.</div>
        </div>
        <div class="feature">
          <div class="feature__icon">📂</div>
          <div class="feature__title">Native folder picker</div>
          <div class="feature__desc">A real file browser dialog — no more typing paths by hand.</div>
        </div>
        <div class="feature">
          <div class="feature__icon">🔑</div>
          <div class="feature__title">Interactive env vars</div>
          <div class="feature__desc">Scans your source, detects required variables, prompts you for values.</div>
        </div>
      </div>
    </div>
  </section>

  <!-- ============================================================ QUICK START -->
  <section class="section section--raised" id="quickstart">
    <div class="container container--narrow">
      <p class="section__eyebrow">Quick start</p>
      <h2 class="section__title">Four steps to live.</h2>

      <ol class="steps">
        <li class="step reveal">
          <span class="step__num">1</span>
          <div class="step__title">Navigate to your project</div>
          <div class="step__term"><span class="t-prompt">$</span>cd my-project</div>
        </li>

        <li class="step reveal">
          <span class="step__num">2</span>
          <div class="step__title">Detect your project</div>
          <div class="step__term">
            <span class="t-prompt">$</span>opun8 detect<br>
            <span class="t-out">✅ Detected: Next.js project</span><br>
            <span class="t-out">📦 Package manager: npm</span><br>
            <span class="t-out">🛠️ Build command: npm run build</span><br>
            <span class="t-out">📁 Output directory: .next</span>
          </div>
        </li>

        <li class="step reveal">
          <span class="step__num">3</span>
          <div class="step__title">Authenticate with your provider</div>
          <div class="step__desc">Pick whichever you're deploying to — GitHub is required for Render deployments.</div>
          <div class="step__term">
            <span class="t-prompt">$</span>opun8 vercel<br>
            <span class="t-prompt">$</span>opun8 netlify<br>
            <span class="t-prompt">$</span>opun8 render<br>
            <span class="t-prompt">$</span>opun8 github
          </div>
        </li>

        <li class="step reveal">
          <span class="step__num">4</span>
          <div class="step__title">Deploy</div>
          <div class="step__term">
            <span class="t-prompt">$</span>opun8 deploy vercel<br>
            <span class="t-out">🚀 Deploying...</span><br>
            <span class="t-out">✅ Deployment complete!</span><br>
            <span class="t-out">🌐 Live at: <span class="t-gold">https://my-project.vercel.app</span></span>
          </div>
        </li>
      </ol>
    </div>
  </section>

  <!-- ============================================================ ENV VARS -->
  <section class="section" id="envvars">
    <div class="container container--narrow">
      <p class="section__eyebrow">Interactive environment variables</p>
      <h2 class="section__title">Opun8 reads your source before it asks you anything.</h2>
      <p class="section__lead">It scans for <code>process.env</code>, <code>os.getenv</code>, and their equivalents across languages, shows exactly where each variable is used, and only prompts for what your project actually needs.</p>

      <div class="terminal terminal--wide reveal">
        <div class="terminal__bar">
          <span class="terminal__dot"></span>
          <span class="terminal__title">opun8 deploy netlify</span>
        </div>
        <div class="terminal__body">
<span class="t-out">🔐 Environment Variables Detected</span>

Select variables to include:
<div class="envrow"><span class="chk">[x]</span><span class="name">DATABASE_URL</span><span class="loc">→ used in app/config.py:15, models/db.py:22</span></div>
<div class="envrow"><span class="chk">[x]</span><span class="name">API_KEY</span><span class="loc">→ used in services/api.py:42</span></div>
<div class="envrow"><span class="chk chk--off">[ ]</span><span class="name">SECRET_KEY</span><span class="loc">→ used in app/settings.py:8</span></div>

<div class="env-divider"></div>
<div class="env-cmdlist">
  <b>&lt;number&gt;</b>  Toggle selection
  <b>a</b>         Select all
  <b>n</b>         Select none
  <b>d</b>         Done — proceed with selected
  <b>q</b>         Cancel
</div>
<div class="env-divider"></div>

Enter value for DATABASE_URL: <span class="t-out">postgres://...</span>
Enter value for API_KEY: <span class="masked">********</span>

<span class="t-out">✅ Selected 2 environment variable(s) for deployment</span>
<span class="t-out">🔒 1 sensitive value(s) hidden from display</span>
        </div>
      </div>
    </div>
  </section>

  <!-- ============================================================ PROVIDERS -->
  <section class="section section--raised" id="providers">
    <div class="container">
      <p class="section__eyebrow">Provider support</p>
      <h2 class="section__title">Built for how each platform actually works.</h2>

      <div class="grid grid--providers">
        <div class="provider reveal">
          <div class="provider__head"><span class="provider__title">▲ Vercel</span></div>
          <ul>
            <li><span class="ck">✅</span>OAuth 2.0 + PKCE authentication</li>
            <li><span class="ck">✅</span>Project creation and management</li>
            <li><span class="ck">✅</span>File upload and deployment</li>
            <li><span class="ck">✅</span>Environment variable management</li>
            <li><span class="ck">✅</span>Cost estimation</li>
            <li><span class="ck">✅</span>URL renaming</li>
          </ul>
        </div>

        <div class="provider reveal">
          <div class="provider__head">
            <span class="provider__title">📦 Netlify</span>
            <span class="provider__tag">NEW v0.1.5</span>
          </div>
          <ul>
            <li><span class="ck">✅</span>OAuth 2.0 authentication</li>
            <li><span class="ck">✅</span>Site creation and management</li>
            <li><span class="ck">✅</span>File upload and deployment</li>
            <li><span class="ck">✅</span>Environment variable management</li>
            <li><span class="ck">✅</span>Credit-based cost estimation</li>
            <li><span class="ck">✅</span>Interactive name conflict resolution</li>
            <li><span class="ck">✅</span>Personal Access Token support</li>
          </ul>
        </div>

        <div class="provider reveal">
          <div class="provider__head"><span class="provider__title">☁️ Render</span></div>
          <ul>
            <li><span class="ck">✅</span>GitHub repository deployment</li>
            <li><span class="ck">✅</span>Service creation and management</li>
            <li><span class="ck">✅</span>Environment variable management</li>
            <li><span class="ck">✅</span>Deployment status polling</li>
            <li><span class="ck">✅</span>Interactive name conflict resolution</li>
          </ul>
        </div>

        <div class="provider reveal">
          <div class="provider__head"><span class="provider__title">🐙 GitHub</span></div>
          <ul>
            <li><span class="ck">✅</span>Repository listing</li>
            <li><span class="ck">✅</span>Repository cloning</li>
            <li><span class="ck">✅</span>Push to GitHub</li>
          </ul>
        </div>
      </div>
    </div>
  </section>

  <!-- ============================================================ COST -->
  <section class="section" id="cost">
    <div class="container">
      <p class="section__eyebrow">Cost estimator</p>
      <h2 class="section__title">Know the bill before you ship.</h2>
      <p class="section__lead">Opun8 shows you deployment costs before you deploy — no surprises at the end of the month.</p>

      <div class="grid grid--cost">
        <div class="terminal reveal">
          <div class="terminal__bar">
            <span class="terminal__dot"></span>
            <span class="terminal__title">▲ Vercel cost estimate</span>
          </div>
          <div class="terminal__body">
            <div class="cost-meta">Plan: Pro</div>
            <div class="cost-row"><span class="lbl">Seats</span><span class="val">$20.00</span></div>
            <div class="cost-row"><span class="lbl">Bandwidth</span><span class="val">$0.00</span></div>
            <div class="cost-row"><span class="lbl">Build minutes</span><span class="val">$0.00</span></div>
            <div class="cost-row"><span class="lbl">Functions</span><span class="val">$0.00</span></div>
            <div class="cost-divider"></div>
            <div class="cost-row cost-row--total"><span class="lbl">Total</span><span class="val">$20.00/mo</span></div>
          </div>
        </div>

        <div class="terminal reveal">
          <div class="terminal__bar">
            <span class="terminal__dot"></span>
            <span class="terminal__title">📦 Netlify cost estimate</span>
          </div>
          <div class="terminal__body">
            <div class="cost-meta">Plan: Pro · Credit-based pricing</div>
            <div class="cost-row"><span class="lbl">Plan</span><span class="val">$20.00</span></div>
            <div class="cost-divider"></div>
            <div class="cost-row"><span class="lbl">Bandwidth</span><span class="val">300 credits</span></div>
            <div class="cost-row"><span class="lbl">Compute</span><span class="val">300 credits</span></div>
            <div class="cost-row"><span class="lbl">Web requests</span><span class="val">20 credits</span></div>
            <div class="cost-row"><span class="lbl">Production deploys</span><span class="val">75 credits</span></div>
            <div class="cost-divider"></div>
            <div class="cost-row"><span class="lbl">Credits used</span><span class="val">695 / 3,000</span></div>
            <div class="cost-bar"><div class="cost-bar__fill" style="width:23%"></div></div>
            <div class="cost-note">23% of plan credits used</div>
            <div class="cost-divider"></div>
            <div class="cost-row cost-row--total"><span class="lbl">Total</span><span class="val">$20.00/mo</span></div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ============================================================ COMMANDS -->
  <section class="section section--raised" id="commands">
    <div class="container">
      <p class="section__eyebrow">Commands</p>
      <h2 class="section__title">Everything, typed exactly as shown.</h2>

      <div class="commands">
        <div class="cmd-group">
          <div class="cmd-group__title">Core</div>
          <div class="cmd-row"><code>opun8</code><span>Show welcome screen</span></div>
          <div class="cmd-row"><code>opun8 --version</code><span>Show version</span></div>
          <div class="cmd-row"><code>opun8 doctor</code><span>Check environment</span></div>
          <div class="cmd-row"><code>opun8 detect</code><span>Detect project type</span></div>
          <div class="cmd-row"><code>opun8 deploy</code><span>Deploy your project</span></div>
          <div class="cmd-row"><code>opun8 help</code><span>Show all commands</span></div>
        </div>

        <div class="cmd-group">
          <div class="cmd-group__title">Platform</div>
          <div class="cmd-row"><code>opun8 github</code><span>Connect to GitHub</span></div>
          <div class="cmd-row"><code>opun8 vercel</code><span>Connect to Vercel</span></div>
          <div class="cmd-row"><code>opun8 netlify</code><span>Connect to Netlify</span></div>
          <div class="cmd-row"><code>opun8 render</code><span>Connect to Render</span></div>
          <div class="cmd-row"><code>opun8 vercel --logout</code><span>Disconnect from Vercel</span></div>
          <div class="cmd-row"><code>opun8 netlify --logout</code><span>Disconnect from Netlify</span></div>
          <div class="cmd-row"><code>opun8 render --logout</code><span>Disconnect from Render</span></div>
        </div>

        <div class="cmd-group">
          <div class="cmd-group__title">Deployment</div>
          <div class="cmd-row"><code>opun8 deploy vercel</code><span>Deploy to Vercel</span></div>
          <div class="cmd-row"><code>opun8 deploy netlify</code><span>Deploy to Netlify</span></div>
          <div class="cmd-row"><code>opun8 deploy render</code><span>Deploy to Render</span></div>
        </div>

        <div class="cmd-group">
          <div class="cmd-group__title">Account</div>
          <div class="cmd-row"><code>opun8 register</code><span>Create an account</span></div>
          <div class="cmd-row"><code>opun8 login</code><span>Log in</span></div>
          <div class="cmd-row"><code>opun8 verify</code><span>Verify email with OTP</span></div>
          <div class="cmd-row"><code>opun8 resend-otp</code><span>Resend verification code</span></div>
          <div class="cmd-row"><code>opun8 status</code><span>Check account status</span></div>
          <div class="cmd-row"><code>opun8 upgrade</code><span>Upgrade subscription plan</span></div>
          <div class="cmd-row"><code>opun8 logout</code><span>Logout from all services</span></div>
        </div>

        <div class="cmd-group">
          <div class="cmd-group__title">Advanced</div>
          <div class="cmd-row"><code>opun8 clone</code><span>Clone any website</span></div>
          <div class="cmd-row"><code>opun8 history</code><span>View deployment history</span></div>
          <div class="cmd-row"><code>opun8 badges</code><span>View badge progress</span></div>
        </div>
      </div>
    </div>
  </section>

  <!-- ============================================================ BADGES -->
  <section class="section" id="badges">
    <div class="container">
      <p class="section__eyebrow">Badge system</p>
      <h2 class="section__title">Deploy enough, and Opun8 notices.</h2>
      <p class="section__lead">Every level unlocks at a real deployment count — the order below is exactly how you'll earn them.</p>

      <ol class="ladder">
        <li class="medal"><div class="medal__ring">🌱</div><div class="medal__lvl">LEVEL 1</div><div class="medal__name">First Clone</div><div class="medal__req">1 deployment</div></li>
        <li class="medal"><div class="medal__ring">🔍</div><div class="medal__lvl">LEVEL 2</div><div class="medal__name">Curious Explorer</div><div class="medal__req">3 deployments</div></li>
        <li class="medal"><div class="medal__ring">🧩</div><div class="medal__lvl">LEVEL 3</div><div class="medal__name">Pattern Finder</div><div class="medal__req">5 deployments</div></li>
        <li class="medal"><div class="medal__ring">📚</div><div class="medal__lvl">LEVEL 4</div><div class="medal__name">Archivist</div><div class="medal__req">10 deployments</div></li>
        <li class="medal"><div class="medal__ring">🚀</div><div class="medal__lvl">LEVEL 5</div><div class="medal__name">Speed Runner</div><div class="medal__req">25 deployments</div></li>
        <li class="medal"><div class="medal__ring">🏆</div><div class="medal__lvl">LEVEL 6</div><div class="medal__name">Master Archiver</div><div class="medal__req">50 deployments</div></li>
        <li class="medal"><div class="medal__ring">👑</div><div class="medal__lvl">LEVEL 7</div><div class="medal__name">Clone King</div><div class="medal__req">100 deployments</div></li>
      </ol>
    </div>
  </section>

  <!-- ============================================================ DEVELOP / CONTRIBUTE -->
  <section class="section section--raised" id="develop">
    <div class="container grid grid--split">
      <div class="reveal">
        <p class="section__eyebrow">Development</p>
        <h2 class="section__title">Run it from source.</h2>
        <div class="dev-term">
          <span class="t-out"><span class="t-prompt">$</span>git clone https://github.com/KakesDavid/opun8.git</span>
          <span class="t-out"><span class="t-prompt">$</span>cd opun8</span>
          <span class="t-out"><span class="t-prompt">$</span>python -m venv .venv</span>
          <span class="t-out"><span class="t-prompt">$</span>source .venv/bin/activate</span>
          <span class="t-out"><span class="t-prompt">$</span>pip install -e .</span>
          <span class="t-out"><span class="t-prompt">$</span>pytest</span>
        </div>
      </div>

      <div class="reveal">
        <p class="section__eyebrow">Contributing</p>
        <h2 class="section__title">We read every pull request.</h2>
        <ul class="contrib-list">
          <li><b>1.</b> Fork the repository</li>
          <li><b>2.</b> git checkout -b feature/amazing-feature</li>
          <li><b>3.</b> git commit -m 'Add amazing feature'</li>
          <li><b>4.</b> git push origin feature/amazing-feature</li>
          <li><b>5.</b> Open a Pull Request</li>
        </ul>
        <ul class="help-areas">
          <li>Railway provider</li>
          <li>Documentation</li>
          <li>Tests</li>
          <li>Bug fixes</li>
          <li>UI/UX improvements</li>
        </ul>
      </div>
    </div>
  </section>

  <!-- ============================================================ FOOTER -->
  <footer class="footer">
    <div class="container footer__inner">
      <div class="footer__brand">🦉 Opun8</div>
      <p class="footer__tag">Built with ❤️ by <a href="https://github.com/KakesDavid" class="gold-text">Kakes David</a> and the Opun8 community.</p>
      <div class="footer__cta">
        <a class="btn btn--primary" href="https://github.com/KakesDavid/opun8/stargazers">★ Star us on GitHub</a>
      </div>
      <div class="footer__meta">
        <a href="https://opun8.dev/docs">Documentation</a>
        <a href="https://github.com/KakesDavid/opun8/issues">Report bug</a>
        <a href="https://github.com/KakesDavid/opun8/issues">Request feature</a>
        <a href="https://github.com/KakesDavid/opun8/blob/main/LICENSE">MIT License</a>
      </div>
    </div>
  </footer>

<script>
(function(){
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- scroll reveal ---------- */
  var revealEls = document.querySelectorAll('.reveal');
  if (reduceMotion || !('IntersectionObserver' in window)) {
    revealEls.forEach(function(el){ el.classList.add('is-visible'); });
  } else {
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(entry){
        if (entry.isIntersecting){
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    revealEls.forEach(function(el){ io.observe(el); });
  }

  /* ---------- copy button ---------- */
  document.querySelectorAll('[data-copy]').forEach(function(btn){
    btn.addEventListener('click', function(){
      var text = btn.getAttribute('data-copy');
      var restore = function(){
        var label = btn.querySelector('.btn__copy-label');
        if (label) label.textContent = 'copy';
        btn.classList.remove('copied');
      };
      var onCopied = function(){
        var label = btn.querySelector('.btn__copy-label');
        if (label) label.textContent = 'copied ✓';
        btn.classList.add('copied');
        setTimeout(restore, 1800);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(onCopied).catch(function(){});
      } else {
        var ta = document.createElement('textarea');
        ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); onCopied(); } catch(e){}
        document.body.removeChild(ta);
      }
    });
  });

  /* ---------- hero terminal typewriter ---------- */
  var host = document.getElementById('hero-terminal');
  if (!host) return;

  var script = [
    { type:'cmd', text:'cd my-project' },
    { type:'cmd', text:'opun8 detect' },
    { type:'out', text:'✅ Detected: Next.js project' },
    { type:'out', text:'📦 Package manager: npm' },
    { type:'out', text:'🛠️ Build command: npm run build' },
    { type:'out', text:'📁 Output directory: .next' },
    { type:'blank' },
    { type:'cmd', text:'opun8 deploy vercel' },
    { type:'out', text:'🚀 Deploying...' },
    { type:'out', text:'✅ Deployment complete!' },
    { type:'out', text:'🌐 Live at: ', gold:'https://my-project.vercel.app' }
  ];

  function renderInstant(){
    script.forEach(function(line){
      var div = document.createElement('div');
      div.className = 't-line';
      if (line.type === 'blank'){ div.innerHTML = '&nbsp;'; }
      else if (line.type === 'cmd'){
        div.innerHTML = '<span class="t-prompt">➜</span>' + line.text;
      } else {
        div.className += ' t-out';
        div.textContent = line.text || '';
        if (line.gold){
          var span = document.createElement('span');
          span.className = 't-gold';
          span.textContent = line.gold;
          div.appendChild(span);
        }
      }
      host.appendChild(div);
    });
    var cursor = document.createElement('span');
    cursor.className = 't-cursor';
    host.lastChild.appendChild(cursor);
  }

  function typeLines(i){
    if (i >= script.length){
      var cursor = document.createElement('span');
      cursor.className = 't-cursor';
      host.lastChild.appendChild(cursor);
      return;
    }
    var line = script[i];
    var div = document.createElement('div');
    div.className = 't-line' + (line.type === 'out' ? ' t-out' : '');
    host.appendChild(div);

    if (line.type === 'blank'){
      div.innerHTML = '&nbsp;';
      setTimeout(function(){ typeLines(i + 1); }, 220);
      return;
    }

    var prefix = '';
    if (line.type === 'cmd'){
      var promptSpan = document.createElement('span');
      promptSpan.className = 't-prompt';
      promptSpan.textContent = '➜';
      div.appendChild(promptSpan);
    }

    var textNode = document.createElement('span');
    div.appendChild(textNode);

    var chars = (line.text || '').split('');
    var ci = 0;
    (function typeChar(){
      if (ci < chars.length){
        textNode.textContent += chars[ci];
        ci++;
        setTimeout(typeChar, 22);
      } else if (line.gold){
        var goldSpan = document.createElement('span');
        goldSpan.className = 't-gold';
        div.appendChild(goldSpan);
        var gchars = line.gold.split('');
        var gi = 0;
        (function typeGold(){
          if (gi < gchars.length){
            goldSpan.textContent += gchars[gi];
            gi++;
            setTimeout(typeGold, 16);
          } else {
            setTimeout(function(){ typeLines(i + 1); }, 260);
          }
        })();
      } else {
        setTimeout(function(){ typeLines(i + 1); }, line.type === 'cmd' ? 160 : 90);
      }
    })();
  }

  if (reduceMotion){
    renderInstant();
  } else {
    typeLines(0);
  }
})();
</script>

</body>
</html>