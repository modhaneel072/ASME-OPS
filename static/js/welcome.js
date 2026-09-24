/*  ASME at Iowa — welcome page
    Two moments: the shop light coming on across the rack (load), and the
    inspection run (scroll): each bar pulled onto the bench in turn, its
    sheet written on as you scroll. Everything else on the page is still.  */
(() => {
  const hero = document.querySelector('.hero');
  const rack = document.getElementById('rack');
  if (!hero || !rack) return;

  const bars = Array.from(rack.querySelectorAll('.bar'));
  const pulls = bars.map((b) => b.querySelector('.bar-pull'));
  const h1 = document.querySelector('h1.h1');
  const cue = document.querySelector('.h1-cue-block');
  const deck = document.querySelector('.deck');
  const ctas = document.querySelector('.cta-row');
  const live = document.getElementById('rack-live');
  const run = document.getElementById('inspect');
  const stage = run && run.querySelector('.inspect-stage');
  const frames = run ? Array.from(run.querySelectorAll('.inspect')) : [];

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const phone = () => window.matchMedia('(max-width: 767px)').matches;
  const hasGsap = typeof window.gsap !== 'undefined';
  if (hasGsap) {
    if (window.ScrollToPlugin) gsap.registerPlugin(ScrollToPlugin);
    if (window.ScrollTrigger) gsap.registerPlugin(ScrollTrigger);
    if (window.SplitText) gsap.registerPlugin(SplitText);
  }

  // ── Smooth scroll, driven by GSAP's ticker so ScrollTrigger stays in step
  let lenis = null;
  if (window.Lenis && hasGsap && !reduce && !phone()) {
    lenis = new window.Lenis({ duration: 1.0, smoothWheel: true });
    window.__asmeLenis = lenis;
    if (window.ScrollTrigger) lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add((t) => lenis.raf(t * 1000));
    gsap.ticker.lagSmoothing(0);
  }
  const scrollToY = (y, onDone) => {
    if (lenis) { lenis.scrollTo(y, { duration: 1.1, onComplete: onDone }); return; }
    if (hasGsap && window.ScrollToPlugin && !reduce) { gsap.to(window, { scrollTo: y, duration: 0.9, ease: 'power3.inOut', onComplete: onDone }); return; }
    window.scrollTo({ top: y, behavior: reduce ? 'auto' : 'smooth' });
    if (onDone) setTimeout(onDone, reduce ? 0 : 500);
  };

  // ── Rack state ──────────────────────────────────────────────────────
  let pulled = null;     // the bar under the light
  let pinned = false;    // pulled by tap / keyboard / a link, so pointerleave leaves it
  let pointerSeen = false;
  let demoBar = null;    // the bar the load sequence pulled as a demonstration

  const lit = (els, value, duration) => {
    if (!hasGsap) { els.forEach((el) => el.style.setProperty('--lit', value)); return; }
    gsap.to(els, { '--lit': value, duration: reduce ? 0 : duration, ease: 'power2.out', overwrite: 'auto' });
  };

  // Move the streak so the light physically sits on the pulled bar.
  const streakTo = (bar) => {
    if (!hasGsap || reduce) return;
    const h = hero.getBoundingClientRect();
    const r = bar.getBoundingClientRect();
    const pct = phone()
      ? ((r.top + r.height / 2 - h.top) / h.height) * 100
      : ((r.left + r.width / 2 - h.left) / h.width) * 100;
    gsap.to(hero, { '--lx': `${pct.toFixed(1)}%`, duration: 0.6, ease: 'power3.out', overwrite: 'auto' });
  };

  const takeOverLighting = () => {
    const load = window.__asmeWelcomeTl;
    if (!load || !load.isActive()) return;
    gsap.getTweensOf(bars).forEach((t) => { if ('--lit' in t.vars) t.kill(); });
    gsap.getTweensOf(hero).forEach((t) => { if ('--lx' in t.vars) t.kill(); });
  };

  function pull(bar, opts = {}) {
    if (opts.pin) pinned = true;
    if (pulled === bar) return;
    takeOverLighting();
    if (demoBar && demoBar !== bar && hasGsap) gsap.to(demoBar, { x: 0, duration: 0.3, overwrite: 'auto' });
    pulled = bar;
    bars.forEach((b, i) => {
      const on = b === bar;
      b.classList.toggle('is-pulled', on);
      b.classList.toggle('is-dim', !on);
      pulls[i].setAttribute('aria-expanded', on ? 'true' : 'false');
    });
    lit([bar], 1, 0.45);
    lit(bars.filter((b) => b !== bar), 0.12, 0.55);
    streakTo(bar);
    // Announce only deliberate pulls (keyboard, tap, link); hover would be chatty.
    if (live && opts.pin) live.textContent = `${bar.dataset.name}, ${bar.dataset.role}.`;
  }

  function release() {
    if (!pulled) return;
    takeOverLighting();
    if (demoBar && hasGsap) gsap.to(demoBar, { x: 0, duration: 0.3, overwrite: 'auto' });
    demoBar = null;
    pulled = null;
    pinned = false;
    bars.forEach((b, i) => {
      b.classList.remove('is-pulled', 'is-dim');
      pulls[i].setAttribute('aria-expanded', 'false');
    });
    lit(bars, 0.3, 0.5);
    if (hasGsap && !reduce) gsap.to(hero, { '--lx': '30%', duration: 0.8, ease: 'power3.out', overwrite: 'auto' });
    if (live) live.textContent = '';
  }

  // Jump to a member's frame in the inspection run (set up below).
  let jumpToFrame = null;

  // ── Input: bound before the load timeline so a fast visitor is never locked out
  bars.forEach((bar, i) => {
    bar.addEventListener('pointerenter', (e) => {
      if (e.pointerType === 'touch') return;
      pointerSeen = true;
      if (pinned && pulled && pulled !== bar) pinned = false;
      // Focus left on a previously clicked bar would otherwise hold it open.
      const focused = document.activeElement && document.activeElement.closest('.bar');
      if (focused && focused !== bar) document.activeElement.blur();
      pull(bar);
    });
    pulls[i].addEventListener('click', () => {
      // Pointer users already see the panel on hover: a click goes to the sheet.
      // Touch: first tap pulls, second tap goes to the sheet.
      if (pulled === bar && jumpToFrame) { jumpToFrame(i); return; }
      pull(bar, { pin: true });
    });
  });
  rack.addEventListener('pointerleave', () => { if (!pinned) release(); });

  rack.addEventListener('focusin', (e) => {
    const bar = e.target.closest('.bar');
    if (bar) pull(bar, { pin: true });
  });
  rack.addEventListener('focusout', (e) => {
    if (!rack.contains(e.relatedTarget)) { pinned = false; if (!rack.matches(':hover')) release(); }
  });
  rack.addEventListener('keydown', (e) => {
    const idx = pulls.indexOf(document.activeElement);
    if (e.key === 'Escape') {
      const bar = e.target.closest('.bar');
      if (bar) pulls[bars.indexOf(bar)].focus({ preventScroll: true });
      release();
      return;
    }
    if (idx < 0) return;
    const next = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? idx + 1
      : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? idx - 1
      : e.key === 'Home' ? 0 : e.key === 'End' ? pulls.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    pulls[(next + pulls.length) % pulls.length].focus();
  });

  // Links further down the page go to the person's sheet instead of leaving the page.
  document.querySelectorAll('[data-pull]').forEach((a) => {
    a.addEventListener('click', (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const i = bars.findIndex((b) => b.dataset.slug === a.dataset.pull);
      if (i < 0 || !jumpToFrame) return;   // the in-page #inspect-<slug> anchor is the fallback
      e.preventDefault();
      jumpToFrame(i);
    });
  });

  window.matchMedia('(max-width: 767px)').addEventListener('change', release);

  // ── The inspection run ──────────────────────────────────────────────
  // Desktop: the section pins for one viewport per member and a single
  // scrubbed timeline pulls each bar onto the bench and writes its sheet.
  // Phones and tablets: the frames stack, each lit and written as it scrolls in.
  if (hasGsap && window.ScrollTrigger && run && frames.length && !reduce) {
    const mm = gsap.matchMedia();

    mm.add('(min-width: 768px)', () => {
      run.classList.add('is-pinned');
      const STEP = 1.35;           // timeline seconds per member
      const SCROLL_PER_MEMBER = 0.42; // viewports of scroll per member: one wheel flick each, twelve people in ~5 screens
      const n = frames.length;
      const now = document.getElementById('inspect-now');
      const ticks = Array.from(run.querySelectorAll('.rail-tick'));
      const splits = [];

      const tl = gsap.timeline({
        defaults: { ease: 'power2.out' },
        scrollTrigger: {
          trigger: run,
          start: 'top top',
          end: () => `+=${Math.round(n * SCROLL_PER_MEMBER * 100)}%`,
          pin: true,
          scrub: 0.5,
          snap: { snapTo: 'labels', duration: { min: 0.12, max: 0.35 }, delay: 0.04, ease: 'power1.inOut' },
          onUpdate: (self) => {
            // sheet i owns the stretch from just after its bar arrives to just after the next one starts
            const i = Math.min(n - 1, Math.max(0, Math.floor(self.progress * n - 0.18)));
            if (now) now.textContent = String(i + 1).padStart(2, '0');
            ticks.forEach((t, k) => t.classList.toggle('is-active', k === i));
          },
        },
      });
      window.__asmeInspectTl = tl;

      frames.forEach((frame, i) => {
        const bar = frame.querySelector('.inspect-bar');
        const name = frame.querySelector('.sheet-name');
        const role = frame.querySelector('.sheet-role');
        const lines = Array.from(frame.querySelectorAll('.sheet-line'));
        const contact = frame.querySelector('.sheet-contact');
        const base = i * STEP;

        let nameParts = [name];
        if (window.SplitText) {
          try { const sp = SplitText.create(name, { type: 'words,chars', wordsClass: 'w', charsClass: 'c' }); splits.push(sp); nameParts = sp.chars; } catch (_) { /* keep whole */ }
        }

        tl.set(frame, { autoAlpha: 1, xPercent: 0 }, base);
        // The bar is pulled from the rack (enters from the right) and the light rakes it.
        tl.fromTo(bar, { x: '55vw', '--lit': 0 }, { x: 0, '--lit': 1, duration: 0.5, ease: 'power3.out' }, base);
        tl.fromTo(frame, { '--kb': 1.08 }, { '--kb': 1, duration: STEP, ease: 'none' }, base);
        tl.fromTo(stage, { '--lx': '-20%' }, { '--lx': '120%', duration: 0.9, ease: 'none' }, base);
        // The sheet is written: name stamped, role set, three lines wiped on, contact last.
        tl.fromTo(nameParts, { yPercent: 110, opacity: 0 }, { yPercent: 0, opacity: 1, duration: 0.35, stagger: { each: 0.018, from: 'start' }, ease: 'power3.out' }, base + 0.12);
        tl.fromTo(role, { autoAlpha: 0, x: 24 }, { autoAlpha: 1, x: 0, duration: 0.25 }, base + 0.3);
        lines.forEach((ln, k) => {
          tl.fromTo(ln, { clipPath: 'inset(0 100% 0 0)', x: -6 }, { clipPath: 'inset(0 0% 0 0)', x: 0, duration: 0.26, ease: 'none' }, base + 0.42 + k * 0.2);
        });
        tl.fromTo(contact, { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.2 }, base + 1.02);
        tl.addLabel(`m${i}`, base + 1.12);
        // Hold, then the whole frame slides off to the left as the next bar arrives.
        if (i < n - 1) {
          tl.to(frame, { xPercent: -28, autoAlpha: 0, duration: 0.35, ease: 'power2.in' }, base + STEP);
        }
      });

      jumpToFrame = (i) => {
        const st = tl.scrollTrigger;
        const y = st.start + (tl.labels[`m${i}`] / tl.duration()) * (st.end - st.start);
        scrollToY(Math.round(y));
      };
      ticks.forEach((t, k) => t.addEventListener('click', () => jumpToFrame(k)));
      const skip = run.querySelector('.inspect-skip');
      if (skip) skip.addEventListener('click', (e) => {
        e.preventDefault();
        const bench = document.querySelector('.bench');
        if (bench) scrollToY(Math.round(bench.getBoundingClientRect().top + window.scrollY - 8));
      });

      return () => { splits.forEach((s) => s.revert()); run.classList.remove('is-pinned'); jumpToFrame = null; };
    });

    mm.add('(max-width: 767px)', () => {
      const cardTls = frames.map((frame) => {
        const bar = frame.querySelector('.inspect-bar');
        const lines = Array.from(frame.querySelectorAll('.sheet-line'));
        const t = gsap.timeline({
          defaults: { ease: 'none' },
          scrollTrigger: { trigger: frame, start: 'top 85%', end: 'top 30%', scrub: true },
        });
        t.fromTo(bar, { '--lit': 0.2 }, { '--lit': 1, duration: 0.5 }, 0);
        lines.forEach((ln, k) => t.fromTo(ln, { clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0)', duration: 0.28 }, 0.15 + k * 0.22));
        return t;
      });
      jumpToFrame = (i) => scrollToY(frames[i].getBoundingClientRect().top + window.scrollY - 12);
      return () => { cardTls.forEach((t) => t.kill()); jumpToFrame = null; };
    });

    // The build codes drift a little with the scroll so the bands read as shelves passing.
    mm.add('(min-width: 768px)', () => {
      document.querySelectorAll('.band-code').forEach((code) => {
        gsap.fromTo(code, { x: '-4vw' }, { x: '4vw', ease: 'none', scrollTrigger: { trigger: code.closest('.band'), start: 'top bottom', end: 'bottom top', scrub: true } });
      });
    });
  } else if (run) {
    // No motion: frames stack and everything is simply visible.
    jumpToFrame = (i) => frames[i].scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }

  // ── The load sequence ───────────────────────────────────────────────
  const finalState = () => {
    hero.style.setProperty('--lx', '30%');
    bars.forEach((b) => { b.style.setProperty('--lit', '0.3'); b.style.transform = ''; });
    document.documentElement.classList.remove('pre-motion');
  };

  let seen = false;
  try { seen = sessionStorage.getItem('asme-welcome-lit') === '1'; sessionStorage.setItem('asme-welcome-lit', '1'); } catch (_) { /* private mode */ }

  // No motion, or a returning visitor in this session: the finished page, no blank frame.
  if (!hasGsap || reduce || seen) { finalState(); return; }

  // Drop the CSS pre-motion state before GSAP reads the bars, or it caches the
  // stylesheet's translateX(115%) as a pixel offset and only ever animates xPercent.
  document.documentElement.classList.remove('pre-motion');
  gsap.set(hero, { '--lx': '-30%' });
  gsap.set(bars, { '--lit': 0, x: 0, xPercent: 115 });
  gsap.set([deck, ctas, cue], { autoAlpha: 0 });
  if (h1) gsap.set(h1, { autoAlpha: 0 });

  const fontsReady = Promise.race([
    (document.fonts && document.fonts.ready) || Promise.resolve(),
    new Promise((r) => setTimeout(r, 600)),
  ]);

  fontsReady.then(() => {
    let chars = null;
    if (h1 && window.SplitText) {
      try {
        const split = SplitText.create(h1, { type: 'words,chars', wordsClass: 'w', charsClass: 'c' });
        chars = split.chars;
      } catch (_) { chars = null; }
    }
    gsap.set(h1, { autoAlpha: 1 });

    const tl = gsap.timeline({ defaults: { ease: 'power2.out' } });
    window.__asmeWelcomeTl = tl;   // exposed so the sequence can be scrubbed from devtools

    // Stock is racked from the right, leftmost travelling farthest.
    tl.to(bars, { xPercent: 0, duration: 0.9, stagger: { each: 0.055, from: 'start' }, ease: 'back.out(1.1)' }, 0);
    // The light comes on and rakes across plate and rack.
    tl.to(hero, { '--lx': '130%', duration: 1.4, ease: 'power2.inOut' }, 0.25);
    // Each bar flares gold as the streak reaches it, then settles to grey-silver.
    tl.to(bars, { '--lit': 1, duration: 0.3, stagger: { each: 0.11, from: 'start' }, ease: 'power1.out' }, 0.38);
    tl.to(bars, { '--lit': 0.3, duration: 0.7, stagger: { each: 0.11, from: 'start' }, ease: 'power2.out' }, 0.6);
    // The headline is cut into the plate left to right, no slide.
    if (chars) {
      tl.fromTo(chars, { opacity: 0, scaleY: 0.88, transformOrigin: '50% 100%' },
        { opacity: 1, scaleY: 1, duration: 0.45, stagger: 0.011, ease: 'power3.out' }, 0.5);
    } else {
      tl.fromTo(h1, { opacity: 0 }, { opacity: 1, duration: 0.6 }, 0.5);
    }
    tl.to([cue, deck, ctas], { autoAlpha: 1, duration: 0.5, ease: 'power1.out' }, 1.5);
    // Demonstrate "pull one from the rack" once, unless the visitor already has.
    tl.add(() => {
      if (pointerSeen || pulled || phone()) {
        // The light comes to rest where every other path leaves it.
        gsap.to(hero, { '--lx': '30%', duration: 0.9, ease: 'power2.out', overwrite: 'auto' });
        return;
      }
      demoBar = bars[0];
      pull(bars[0]);
      gsap.to(bars[0], { x: -10, duration: 0.6, ease: 'back.out(1.8)' });
    }, 1.95);

    // Any input finishes the sequence quickly.
    const hurry = () => { if (tl.isActive()) tl.timeScale(4); };
    ['pointermove', 'keydown', 'wheel', 'touchstart'].forEach((ev) =>
      window.addEventListener(ev, hurry, { once: true, passive: true }));

    // The rack's height settles after fonts and images; keep ScrollTrigger honest.
    if (window.ScrollTrigger) { tl.eventCallback('onComplete', () => ScrollTrigger.refresh()); window.addEventListener('load', () => ScrollTrigger.refresh()); }
  });
})();
