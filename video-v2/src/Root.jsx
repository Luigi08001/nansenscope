import React from 'react';
import {
  AbsoluteFill, Audio, Img, Sequence, useVideoConfig,
  interpolate, spring, useCurrentFrame, staticFile,
} from 'remotion';

/* ── Brand tokens ── */
const C = {
  bg: '#060B14',
  teal: '#00E5A0',
  tealDim: 'rgba(0,229,160,0.12)',
  tealBorder: 'rgba(0,229,160,0.3)',
  tealGlow: 'rgba(0,229,160,0.25)',
  blue: '#0088FF',
  blueDim: 'rgba(0,136,255,0.08)',
  orange: '#FFB800',
  white: '#F0F4F8',
  gray: '#8B95A5',
  dark: '#0D1117',
};

const FONT = "'Inter', 'SF Pro Display', -apple-system, sans-serif";
const MONO = "'JetBrains Mono', 'SF Mono', monospace";

/* ── Animated background with particles + orbs ── */
const AnimatedBg = ({frame}) => {
  const orbs = [
    {speed: 0.008, size: 700, color: C.tealGlow, blur: 100, ox: 200, oy: 100},
    {speed: 0.012, size: 500, color: 'rgba(0,136,255,0.12)', blur: 90, ox: -300, oy: -200},
    {speed: 0.006, size: 400, color: 'rgba(255,184,0,0.06)', blur: 80, ox: 400, oy: 300},
    {speed: 0.015, size: 300, color: 'rgba(0,229,160,0.1)', blur: 70, ox: -100, oy: -300},
  ];

  // Grid lines moving
  const gridOffset = (frame * 0.5) % 60;

  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', inset: 0, background: C.bg}} />

      {/* Moving grid */}
      <div style={{
        position: 'absolute', inset: 0, opacity: 0.04,
        backgroundImage: `linear-gradient(${C.teal} 1px, transparent 1px), linear-gradient(90deg, ${C.teal} 1px, transparent 1px)`,
        backgroundSize: '60px 60px',
        backgroundPosition: `0 ${gridOffset}px`,
      }} />

      {/* Floating orbs */}
      {orbs.map((o, i) => {
        const x = Math.sin(frame * o.speed + i * 1.5) * 350 + 960 + o.ox;
        const y = Math.cos(frame * o.speed * 0.8 + i * 2) * 250 + 540 + o.oy;
        const pulse = 1 + Math.sin(frame * 0.02 + i) * 0.15;
        return (
          <div key={i} style={{
            position: 'absolute',
            width: o.size * pulse, height: o.size * pulse, borderRadius: '50%',
            background: `radial-gradient(circle, ${o.color} 0%, transparent 70%)`,
            left: x - (o.size * pulse) / 2, top: y - (o.size * pulse) / 2,
            filter: `blur(${o.blur}px)`,
          }} />
        );
      })}

      {/* Floating particles */}
      {Array.from({length: 20}).map((_, i) => {
        const px = ((frame * (0.3 + i * 0.05) + i * 97) % 1920);
        const py = ((frame * (0.15 + i * 0.02) + i * 53) % 1080);
        const size = 2 + (i % 3);
        const opacity = 0.15 + Math.sin(frame * 0.03 + i) * 0.1;
        return (
          <div key={`p${i}`} style={{
            position: 'absolute', left: px, top: py,
            width: size, height: size, borderRadius: '50%',
            background: i % 3 === 0 ? C.teal : i % 3 === 1 ? C.blue : C.orange,
            opacity,
          }} />
        );
      })}

      {/* Scan line */}
      <div style={{
        position: 'absolute', left: 0, right: 0,
        top: ((frame * 1.2) % 1200) - 60,
        height: 120,
        background: `linear-gradient(180deg, transparent, rgba(0,229,160,0.03), transparent)`,
        pointerEvents: 'none',
      }} />
    </AbsoluteFill>
  );
};

/* ── Reusable components ── */

/* Word-by-word text reveal */
const WordReveal = ({text, delay = 0, interval = 3, fontSize = 64, color = C.white, fontWeight = 800, highlight = null}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const words = text.split(' ');
  return (
    <div style={{display: 'flex', flexWrap: 'wrap', gap: '0 14px', lineHeight: 1.15}}>
      {words.map((word, i) => {
        const d = delay + i * interval;
        const opacity = interpolate(frame, [d, d + 6], [0, 1], {
          extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
        });
        const y = interpolate(frame, [d, d + 6], [20, 0], {
          extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
        });
        const scale = interpolate(frame, [d, d + 4, d + 8], [0.7, 1.08, 1], {
          extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
        });
        const isHighlight = highlight && word.replace(/[.,!?]/g, '').toLowerCase() === highlight.toLowerCase();
        const wordColor = isHighlight ? C.teal : color;
        const glow = isHighlight ? `0 0 30px ${C.tealGlow}` : 'none';
        return (
          <span key={i} style={{
            opacity, transform: `translateY(${y}px) scale(${scale})`,
            display: 'inline-block', fontFamily: FONT, fontSize, fontWeight, color: wordColor,
            textShadow: glow,
          }}>{word}</span>
        );
      })}
    </div>
  );
};

/* Typewriter text effect */
const Typewriter = ({text, delay = 0, speed = 1.2, fontSize = 22, color = C.gray}) => {
  const frame = useCurrentFrame();
  const chars = Math.floor(interpolate(frame, [delay, delay + text.length / speed], [0, text.length], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  }));
  const cursorBlink = Math.sin(frame * 0.3) > 0;
  return (
    <div style={{fontFamily: MONO, fontSize, color, lineHeight: 1.6}}>
      {text.substring(0, chars)}
      {chars < text.length && cursorBlink && (
        <span style={{display: 'inline-block', width: 2, height: fontSize, background: C.teal, marginLeft: 2, verticalAlign: 'middle'}} />
      )}
    </div>
  );
};

/* Glowing highlight text */
const GlowText = ({children, delay = 0, fontSize = 48, color = C.teal}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: frame - delay, fps, from: 0.5, to: 1, durationInFrames: 20, config: {damping: 8, stiffness: 200}});
  const glow = interpolate(frame, [delay, delay + 15, delay + 30], [0, 30, 15], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  return (
    <span style={{
      display: 'inline-block', fontFamily: FONT, fontSize, fontWeight: 800, color,
      transform: `scale(${s})`, textShadow: `0 0 ${glow}px ${color}`,
    }}>{children}</span>
  );
};

/* Counting text that pops */
const CountPop = ({value, delay = 0, prefix = '', suffix = '', fontSize = 64}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const numVal = parseFloat(value.toString().replace(/[^0-9.]/g, ''));
  const progress = interpolate(frame, [delay, delay + 30], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const eased = 1 - Math.pow(1 - Math.min(progress, 1), 3);
  const current = isNaN(numVal) ? value : (value.toString().includes('.') ? (numVal * eased).toFixed(1) : Math.round(numVal * eased));
  const pop = spring({frame: frame - delay, fps, from: 1.4, to: 1, durationInFrames: 25, config: {damping: 8}});
  const glow = interpolate(frame, [delay + 25, delay + 35], [40, 10], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  return (
    <span style={{
      display: 'inline-block', fontFamily: MONO, fontSize, fontWeight: 800, color: C.teal,
      transform: `scale(${pop})`, textShadow: `0 0 ${glow}px ${C.tealGlow}`,
    }}>{prefix}{current}{suffix}</span>
  );
};

const FadeIn = ({children, delay = 0, duration = 15, direction = 'up', style = {}}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [delay, delay + duration], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const offset = interpolate(frame, [delay, delay + duration], [40, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const transform = direction === 'up' ? `translateY(${offset}px)` :
    direction === 'left' ? `translateX(${offset}px)` :
    direction === 'right' ? `translateX(${-offset}px)` : `translateY(${-offset}px)`;
  return <div style={{opacity, transform, ...style}}>{children}</div>;
};

const Badge = ({text, glow = false}) => (
  <div style={{
    display: 'inline-block', fontFamily: MONO, fontSize: 14, color: C.teal,
    background: C.tealDim, border: `1px solid ${C.tealBorder}`,
    borderRadius: 6, padding: '6px 14px', letterSpacing: 1.5, textTransform: 'uppercase',
    boxShadow: glow ? `0 0 20px ${C.tealGlow}` : 'none',
  }}>{text}</div>
);

const VibeBadge = () => {
  const frame = useCurrentFrame();
  const pulse = 0.85 + Math.sin(frame * 0.05) * 0.15;
  return (
    <div style={{
      position: 'absolute', top: 24, right: 24, fontFamily: MONO, fontSize: 14,
      color: C.teal, background: 'rgba(6,11,20,0.85)', border: `1px solid ${C.tealBorder}`,
      borderRadius: 8, padding: '8px 14px', zIndex: 100, opacity: pulse,
    }}>VIBE CODED &bull; built by Op-Claw</div>
  );
};

/* Animated counter */
const AnimatedNumber = ({value, prefix = '', suffix = '', delay = 0, fontSize = 52, duration = 25}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const numericValue = parseFloat(value.toString().replace(/[^0-9.]/g, ''));
  const isDecimal = value.toString().includes('.');

  if (isNaN(numericValue)) {
    // Non-numeric value -- just fade in
    const opacity = interpolate(frame, [delay, delay + 12], [0, 1], {
      extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
    });
    return (
      <span style={{opacity, fontFamily: MONO, fontSize, fontWeight: 800, color: C.teal}}>
        {prefix}{value}{suffix}
      </span>
    );
  }

  const progress = interpolate(frame, [delay, delay + duration], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const eased = 1 - Math.pow(1 - Math.min(progress, 1), 3); // ease-out cubic
  const current = numericValue * eased;
  const display = isDecimal ? current.toFixed(1) : Math.round(current);

  const scale = spring({
    frame: frame - delay, fps, from: 1.3, to: 1,
    durationInFrames: 20, config: {damping: 10, stiffness: 200},
  });

  return (
    <span style={{
      fontFamily: MONO, fontSize, fontWeight: 800, color: C.teal,
      display: 'inline-block', transform: `scale(${scale})`,
    }}>
      {prefix}{display}{suffix}
    </span>
  );
};

const TerminalLine = ({text, delay, prefix = '$'}) => {
  const frame = useCurrentFrame();
  const chars = Math.floor(interpolate(frame, [delay, delay + 18], [0, text.length], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  }));
  const opacity = interpolate(frame, [delay, delay + 5], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const cursorBlink = Math.sin(frame * 0.3) > 0;
  return (
    <div style={{opacity, fontFamily: MONO, fontSize: 22, color: C.white, marginBottom: 8, lineHeight: 1.6}}>
      <span style={{color: C.teal}}>{prefix} </span>
      {text.substring(0, chars)}
      {chars < text.length && cursorBlink && <span style={{
        display: 'inline-block', width: 10, height: 22, background: C.teal, marginLeft: 2,
      }} />}
    </div>
  );
};

const TerminalOutput = ({lines, startDelay}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{marginTop: 8}}>
      {lines.map((line, i) => {
        const d = startDelay + i * 5;
        const opacity = interpolate(frame, [d, d + 4], [0, 1], {
          extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
        });
        const slideX = interpolate(frame, [d, d + 8], [-20, 0], {
          extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
        });
        return (
          <div key={i} style={{
            opacity, transform: `translateX(${slideX}px)`,
            fontFamily: MONO, fontSize: 18, color: line.color || C.gray,
            marginBottom: 3, lineHeight: 1.5,
          }}>{line.text}</div>
        );
      })}
    </div>
  );
};

/* Animated progress bar */
const ProgressBar = ({value, max, delay, color = C.teal, width = 200}) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [delay, delay + 20], [0, value / max], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  return (
    <div style={{
      width, height: 8, background: 'rgba(255,255,255,0.08)',
      borderRadius: 4, overflow: 'hidden',
    }}>
      <div style={{
        width: `${progress * 100}%`, height: '100%',
        background: `linear-gradient(90deg, ${color}, ${color}88)`,
        borderRadius: 4,
        boxShadow: `0 0 10px ${color}44`,
      }} />
    </div>
  );
};

const ProductImage = ({src, delay = 0, scale = 1, scroll = false, scrollSpeed = 0.3, maxHeight = 500}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: frame - delay, fps, from: 0.85, to: scale, durationInFrames: 25, config: {damping: 15}});
  const opacity = interpolate(frame, [delay, delay + 12], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const floatY = Math.sin((frame - delay) * 0.04) * 4;
  const scrollY = scroll ? Math.max(0, (frame - delay - 15) * scrollSpeed) : 0;
  return (
    <div style={{
      opacity, transform: `scale(${s}) translateY(${floatY}px)`,
      borderRadius: 16, overflow: 'hidden', maxHeight,
      boxShadow: `0 20px 60px rgba(0,0,0,0.5), 0 0 50px ${C.tealGlow}`,
      border: `1px solid ${C.tealBorder}`,
    }}>
      <Img src={src} style={{
        width: '100%', objectFit: 'cover', objectPosition: 'top',
        transform: scroll ? `translateY(-${scrollY}px)` : 'none',
      }} />
    </div>
  );
};

const StatCard = ({label, value, suffix = '', delay, icon}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: frame - delay, fps, from: 0, to: 1, durationInFrames: 20, config: {damping: 12}});
  const floatY = Math.sin((frame - delay) * 0.05) * 3;
  return (
    <div style={{
      opacity: s, transform: `scale(${0.8 + s * 0.2}) translateY(${floatY}px)`,
      background: 'rgba(13,17,23,0.85)', border: `1px solid ${C.tealBorder}`,
      borderRadius: 16, padding: '28px 36px', textAlign: 'center', minWidth: 200,
      boxShadow: `0 8px 32px rgba(0,0,0,0.3), 0 0 20px ${C.tealGlow}`,
      backdropFilter: 'blur(10px)',
    }}>
      {icon && <div style={{fontSize: 28, marginBottom: 8}}>{icon}</div>}
      <AnimatedNumber value={value} suffix={suffix} delay={delay} fontSize={48} />
      <div style={{fontFamily: FONT, fontSize: 15, color: C.gray, marginTop: 10, letterSpacing: 0.5}}>{label}</div>
    </div>
  );
};

/* ── SCENE 1: Hook / Intro (0-4s) ── */
const SceneIntro = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const logoScale = spring({frame, fps, from: 0.3, to: 1, durationInFrames: 30, config: {damping: 10, stiffness: 150}});
  const lineWidth = interpolate(frame, [35, 70], [0, 500], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const rotation = interpolate(frame, [0, 120], [0, 360], {extrapolateRight: 'clamp'});
  const letterSpacing = interpolate(frame, [0, 25], [20, -3], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      {/* Rotating rings */}
      {[300, 400].map((size, ri) => (
        <div key={ri} style={{
          position: 'absolute', width: size, height: size, borderRadius: '50%',
          border: `${ri === 0 ? 2 : 1}px solid ${C.tealBorder}`,
          transform: `rotate(${rotation * (ri === 0 ? 1 : -0.5)}deg)`, opacity: 0.2 + ri * 0.1,
        }}>
          <div style={{
            position: 'absolute', top: -5, left: '50%', width: 10 - ri * 4, height: 10 - ri * 4,
            borderRadius: '50%', background: C.teal, transform: 'translateX(-50%)',
          }} />
        </div>
      ))}

      <div style={{textAlign: 'center', transform: `scale(${logoScale})`}}>
        <FadeIn delay={5}>
          <Badge text="NansenCLI Challenge Week 2" glow />
        </FadeIn>
        <h1 style={{
          fontFamily: FONT, fontSize: 100, fontWeight: 800, color: C.white,
          margin: '20px 0 0', letterSpacing,
          textShadow: `0 0 40px ${C.tealGlow}`,
        }}>
          Nansen<GlowText delay={10} fontSize={100}>Scope</GlowText>
        </h1>
        <FadeIn delay={20}>
          <Typewriter text="Autonomous Smart Money Intelligence" delay={22} speed={2} fontSize={28} color={C.gray} />
        </FadeIn>
        <div style={{
          width: lineWidth, height: 2,
          background: `linear-gradient(90deg, transparent, ${C.teal}, transparent)`,
          margin: '24px auto 0',
          boxShadow: `0 0 15px ${C.tealGlow}`,
        }} />
      </div>
    </AbsoluteFill>
  );
};

/* ── SCENE 2: The Problem (4-8s) ── */
const SceneProblem = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{justifyContent: 'center', padding: '0 120px'}}>
      <FadeIn delay={0} direction="right">
        <Badge text="The Problem" />
      </FadeIn>
      <div style={{margin: '20px 0 0'}}>
        <WordReveal text="On-chain data is noise" delay={8} interval={4} fontSize={68} highlight="noise" />
      </div>
      <FadeIn delay={30}>
        <Typewriter text="Smart money moves fast. By the time you see it on Twitter, it's already priced in." delay={32} speed={1.5} fontSize={24} color={C.gray} />
      </FadeIn>
      <FadeIn delay={55}>
        <div style={{marginTop: 16}}>
          <WordReveal text="You need signal detection that runs while you sleep." delay={58} interval={3} fontSize={28} color={C.orange} highlight="sleep" />
        </div>
      </FadeIn>

      {/* Animated data stream */}
      <div style={{position: 'absolute', right: 80, top: '15%', opacity: 0.2}}>
        {Array.from({length: 15}).map((_, i) => {
          const d = 5 + i * 3;
          const yOff = ((frame - d) * 1.5) % 800;
          const opacity = interpolate(frame, [d, d + 3], [0, 0.7], {
            extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
          }) * interpolate(yOff, [0, 700, 800], [1, 1, 0], {
            extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
          });
          return (
            <div key={i} style={{
              opacity, fontFamily: MONO, fontSize: 13, color: i % 2 === 0 ? C.teal : '#FF4444',
              marginBottom: 3, transform: `translateY(${yOff * 0.3}px)`,
            }}>
              {`0x${(0xA3F + i * 0x1B7).toString(16)}...${(0xDE + i).toString(16)} ${i % 2 === 0 ? '↑' : '↓'} $${(50 + i * 37).toFixed(0)}K`}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/* ── SCENE 3: The Solution — Landing Page (8-16s) ── */
const SceneSolution = () => {
  return (
    <AbsoluteFill style={{display: 'flex', alignItems: 'center', padding: '0 80px'}}>
      <div style={{flex: '0 0 42%', paddingRight: 50}}>
        <FadeIn delay={0} direction="right">
          <Badge text="The Solution" glow />
        </FadeIn>
        <FadeIn delay={8}>
          <h2 style={{fontFamily: FONT, fontSize: 58, fontWeight: 800, color: C.white, margin: '20px 0 0', lineHeight: 1.1}}>
            Nansen<GlowText delay={12} fontSize={58}>Scope</GlowText>
          </h2>
        </FadeIn>
        <div style={{margin: '24px 0', display: 'flex', flexDirection: 'column', gap: 16}}>
          {[
            {n: '18', t: 'CLI commands'},
            {n: '5', t: 'chains supported', s: '+'},
            {n: '6', t: 'signal types'},
          ].map((item, i) => (
            <FadeIn key={i} delay={20 + i * 10} direction="left">
              <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
                <CountPop value={item.n} delay={22 + i * 10} suffix={item.s || ''} fontSize={36} />
                <span style={{fontFamily: FONT, fontSize: 20, color: C.gray}}>{item.t}</span>
              </div>
            </FadeIn>
          ))}
        </div>
        <FadeIn delay={55}>
          <WordReveal text="Detect, verify, and monitor — autonomously." delay={57} interval={3} fontSize={22} color={C.gray} highlight="autonomously." />
        </FadeIn>
      </div>
      <div style={{flex: '0 0 58%'}}>
        <ProductImage src={staticFile('images/landing.png')} delay={12} scroll scrollSpeed={1.2} maxHeight={550} />
      </div>
    </AbsoluteFill>
  );
};

/* ── Terminal window component ── */
const TerminalWindow = ({children, title = 'nansenscope — zsh'}) => (
  <div style={{
    background: 'rgba(13,17,23,0.95)', border: `1px solid ${C.tealBorder}`,
    borderRadius: 16, padding: '24px 32px', width: '100%',
    boxShadow: `0 12px 40px rgba(0,0,0,0.4), 0 0 30px ${C.tealGlow}`,
  }}>
    <div style={{display: 'flex', gap: 8, marginBottom: 14, alignItems: 'center'}}>
      <div style={{width: 12, height: 12, borderRadius: '50%', background: '#FF5F57'}} />
      <div style={{width: 12, height: 12, borderRadius: '50%', background: '#FEBC2E'}} />
      <div style={{width: 12, height: 12, borderRadius: '50%', background: '#28C840'}} />
      <span style={{fontFamily: MONO, fontSize: 13, color: C.gray, marginLeft: 12}}>{title}</span>
    </div>
    {children}
  </div>
);

/* ── SCENE 4a: Terminal — Scan command (16-24s) ── */
const SceneTerminalScan = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{justifyContent: 'center', padding: '40px 80px'}}>
      <FadeIn delay={0}>
        <Badge text="Step 1 — Smart Money Scan" glow />
      </FadeIn>
      <FadeIn delay={6} style={{marginTop: 16}}>
        <TerminalWindow>
          <TerminalLine text="nansenscope scan --chains ethereum,base,solana,arbitrum,bnb" delay={10} />
          <TerminalOutput startDelay={32} lines={[
            {text: '  Scanning smart money across 5 chains...', color: C.gray},
            {text: '  20 API calls | x402 micropayments | ~$0.20 cost', color: C.gray},
          ]} />

          <div style={{margin: '12px 0 8px 16px', display: 'flex', flexDirection: 'column', gap: 8}}>
            {[
              {chain: 'ethereum', signals: 10, top: 'UNI $143M · ONDO $87M · WLD $60M', color: C.teal},
              {chain: 'base',     signals: 10, top: 'VIRTUAL $756K · AERO $926K · TIBBIR $1.4M', color: C.blue},
              {chain: 'solana',   signals: 10, top: 'JUP $2.7M · RENDER $4.5M · META $3.3M', color: C.orange},
              {chain: 'arbitrum', signals: 9,  top: 'ZRO $414K · SQD $229K · ATH $100K', color: '#A78BFA'},
              {chain: 'bnb',      signals: 10, top: 'ALT $1.1M · CAKE $108K · BTCB $249K', color: '#F59E0B'},
            ].map((c, i) => {
              const d = 40 + i * 12;
              return (
                <div key={i}>
                  <div style={{display: 'flex', alignItems: 'center', gap: 12}}>
                    <span style={{fontFamily: MONO, fontSize: 16, color: c.color, width: 90, fontWeight: 700}}>{c.chain}</span>
                    <ProgressBar value={c.signals} max={10} delay={d} color={c.color} width={200} />
                    <AnimatedNumber value={c.signals} delay={d + 2} fontSize={16} duration={12} />
                    <span style={{fontFamily: MONO, fontSize: 13, color: C.gray}}>signals</span>
                  </div>
                  <div style={{
                    fontFamily: MONO, fontSize: 13, color: C.gray, marginLeft: 102, marginTop: 2,
                    opacity: interpolate(frame, [d + 8, d + 14], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
                  }}>{c.top}</div>
                </div>
              );
            })}
          </div>

          <TerminalOutput startDelay={105} lines={[
            {text: '', color: C.gray},
            {text: '  Total signals: 49 | High priority: 30 | Convergence: 0', color: C.white},
            {text: '  Top conviction: UNI (29 SM wallets, $143.8M)', color: C.teal},
          ]} />
        </TerminalWindow>
      </FadeIn>
    </AbsoluteFill>
  );
};

/* ── SCENE 4b: Terminal — More commands (24-34s) ── */
const SceneTerminalMore = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{justifyContent: 'center', padding: '40px 80px'}}>
      <FadeIn delay={0}>
        <Badge text="Step 2 — Perps, Exits, Search" glow />
      </FadeIn>
      <FadeIn delay={6} style={{marginTop: 16}}>
        <TerminalWindow>
          {/* Perps */}
          <TerminalLine text="nansenscope perps" delay={8} />
          <TerminalOutput startDelay={24} lines={[
            {text: '  Hyperliquid — Real-time SM positions', color: C.gray},
          ]} />
          <div style={{margin: '8px 0 12px 16px', display: 'flex', gap: 30}}>
            {[
              {token: 'BTC', pct: 74.2, leverage: '4.2x'},
              {token: 'ETH', pct: 68.1, leverage: '3.8x'},
              {token: 'SOL', pct: 71.5, leverage: '3.1x'},
            ].map((p, i) => (
              <div key={i} style={{display: 'flex', alignItems: 'center', gap: 10}}>
                <span style={{fontFamily: MONO, fontSize: 16, color: C.white, fontWeight: 700}}>{p.token}</span>
                <ProgressBar value={p.pct} max={100} delay={30 + i * 7} color={C.teal} width={120} />
                <AnimatedNumber value={p.pct} suffix="%" delay={32 + i * 7} fontSize={16} duration={12} />
                <span style={{fontFamily: MONO, fontSize: 13, color: C.gray}}>long | {p.leverage}</span>
              </div>
            ))}
          </div>

          {/* Exit signals */}
          <TerminalLine text="nansenscope exit-signals --chains ethereum,base" delay={58} />
          <TerminalOutput startDelay={74} lines={[
            {text: '  Detecting smart money distribution patterns...', color: C.gray},
            {text: '  ethereum done   base done', color: C.teal},
            {text: '  No critical exit signals detected', color: '#28C840'},
          ]} />

          {/* Search */}
          <TerminalLine text='nansenscope search "ethereum whale buying ONDO"' delay={95} />
          <TerminalOutput startDelay={112} lines={[
            {text: '  Searching: "ethereum whale buying ONDO" (limit: 5)', color: C.gray},
            {text: '  Natural language → Nansen API query', color: C.teal},
          ]} />

          {/* DeFi */}
          <TerminalLine text="nansenscope defi --address 0xd8dA6B..." delay={130} />
          <TerminalOutput startDelay={145} lines={[
            {text: '  DeFi Position Analysis — Full wallet breakdown', color: C.gray},
          ]} />

          <TerminalOutput startDelay={155} lines={[
            {text: '  API calls: 30+ | Endpoints: 5 | Cost: ~$0.20', color: C.orange},
          ]} />
        </TerminalWindow>
      </FadeIn>
    </AbsoluteFill>
  );
};

/* ── SCENE 5: Visual Output (reports + charts) ── */
const SceneDashboard = () => {
  return (
    <AbsoluteFill style={{display: 'flex', alignItems: 'center', padding: '0 80px'}}>
      <div style={{flex: '0 0 38%', paddingRight: 40}}>
        <FadeIn delay={0} direction="right">
          <Badge text="Visual Intelligence" glow />
        </FadeIn>
        <div style={{margin: '20px 0'}}>
          <WordReveal text="CLI output becomes visual intelligence" delay={10} interval={3} fontSize={48} highlight="intelligence" />
        </div>
        <FadeIn delay={25}>
          <div style={{display: 'flex', flexDirection: 'column', gap: 14, marginTop: 16}}>
            {['Markdown reports with scores', 'Chain comparison charts', 'Signal timelines', 'Network analysis maps', 'Interactive HTML dashboard'].map((t, i) => (
              <FadeIn key={i} delay={28 + i * 5} direction="left">
                <div style={{display: 'flex', alignItems: 'center', gap: 10}}>
                  <div style={{width: 8, height: 8, borderRadius: '50%', background: C.teal}} />
                  <span style={{fontFamily: FONT, fontSize: 18, color: C.gray}}>{t}</span>
                </div>
              </FadeIn>
            ))}
          </div>
        </FadeIn>
      </div>
      <div style={{flex: '0 0 62%'}}>
        {/* Show real charts instead of empty dashboard */}
        <div style={{display: 'flex', flexDirection: 'column', gap: 14}}>
          <ProductImage src={staticFile('images/signal_timeline.png')} delay={12} scale={0.95} />
          <div style={{display: 'flex', gap: 14}}>
            <div style={{flex: 1}}>
              <ProductImage src={staticFile('images/chain_chart.png')} delay={22} scale={0.95} />
            </div>
            <div style={{flex: 1}}>
              <ProductImage src={staticFile('images/network_map.png')} delay={28} scale={0.95} />
            </div>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ── SCENE 6: Charts + Stats (36-48s) ── */
const SceneCharts = () => {
  return (
    <AbsoluteFill style={{justifyContent: 'center', padding: '0 80px'}}>
      <FadeIn delay={0}>
        <div style={{textAlign: 'center', marginBottom: 30}}>
          <Badge text="Full Workflow" glow />
          <div style={{margin: '14px 0'}}>
            <WordReveal text="Everything you need to trade smarter" delay={5} interval={3} fontSize={54} highlight="smarter" />
          </div>
        </div>
      </FadeIn>

      {/* Stat cards row */}
      <div style={{display: 'flex', gap: 20, justifyContent: 'center', marginBottom: 30}}>
        <StatCard label="CLI Commands" value="18" delay={12} />
        <StatCard label="Chains" value="5" suffix="+" delay={18} />
        <StatCard label="Signal Types" value="6" delay={24} />
        <StatCard label="API Calls / Run" value="30" suffix="+" delay={30} />
      </div>

      {/* Charts row */}
      <FadeIn delay={36}>
        <div style={{display: 'flex', gap: 16, justifyContent: 'center'}}>
          {[
            {src: 'images/chain_chart.png', label: 'Chain Comparison'},
            {src: 'images/signal_timeline.png', label: 'Signal Timeline'},
            {src: 'images/network_map.png', label: 'Network Analysis'},
          ].map((chart, i) => (
            <FadeIn key={i} delay={40 + i * 6} direction="up">
              <div style={{width: 380}}>
                <div style={{
                  borderRadius: 12, overflow: 'hidden', border: `1px solid ${C.tealBorder}`,
                  boxShadow: `0 8px 24px rgba(0,0,0,0.3)`,
                }}>
                  <Img src={staticFile(chart.src)} style={{width: '100%', height: 'auto'}} />
                </div>
                <p style={{fontFamily: MONO, fontSize: 13, color: C.gray, textAlign: 'center', marginTop: 8}}>
                  {chart.label}
                </p>
              </div>
            </FadeIn>
          ))}
        </div>
      </FadeIn>
    </AbsoluteFill>
  );
};

/* ── SCENE 7: Signal to Action (52-62s) ── */
const SceneSignalToAction = () => {
  const frame = useCurrentFrame();

  const steps = [
    {
      phase: 'DETECT', color: C.teal, time: 0,
      title: 'Smart Money Signal Found',
      detail: '29 wallets accumulating UNI — $143M total value',
      cmd: 'nansenscope scan',
    },
    {
      phase: 'VERIFY', color: C.blue, time: 35,
      title: 'Cross-reference signals',
      detail: 'Perps 74% long · No exit signals · Network analysis clean',
      cmd: 'nansenscope perps + exit-signals + network',
    },
    {
      phase: 'ACT', color: C.orange, time: 70,
      title: 'Execution-ready intel',
      detail: 'High conviction score → watchlist or position entry',
      cmd: 'nansenscope watch --token UNI',
    },
    {
      phase: 'MONITOR', color: '#A78BFA', time: 105,
      title: 'Continuous surveillance',
      detail: 'Daily cron re-scans · Alerts if SM starts selling',
      cmd: 'cron: nansenscope daily (09:00 UTC)',
    },
  ];

  return (
    <AbsoluteFill style={{justifyContent: 'center', padding: '0 80px'}}>
      <FadeIn delay={0}>
        <div style={{textAlign: 'center', marginBottom: 36}}>
          <Badge text="The Intelligence Loop" glow />
          <div style={{margin: '14px 0'}}>
            <WordReveal text="Signal → Action" delay={5} interval={6} fontSize={56} highlight="Action" />
          </div>
        </div>
      </FadeIn>

      <div style={{display: 'flex', gap: 20, justifyContent: 'center'}}>
        {steps.map((step, i) => {
          const d = 12 + step.time * 0.3;
          const opacity = interpolate(frame, [d, d + 10], [0, 1], {
            extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
          });
          const slideY = interpolate(frame, [d, d + 12], [50, 0], {
            extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
          });
          const barHeight = interpolate(frame, [d + 8, d + 25], [0, 100], {
            extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
          });

          return (
            <div key={i} style={{
              opacity, transform: `translateY(${slideY}px)`,
              width: 260, display: 'flex', flexDirection: 'column', alignItems: 'center',
            }}>
              {/* Phase badge */}
              <div style={{
                fontFamily: MONO, fontSize: 14, fontWeight: 800, color: step.color,
                background: `${step.color}15`, border: `1px solid ${step.color}40`,
                borderRadius: 8, padding: '8px 16px', marginBottom: 14, letterSpacing: 2,
              }}>{step.phase}</div>

              {/* Card */}
              <div style={{
                background: 'rgba(13,17,23,0.85)', border: `1px solid ${step.color}30`,
                borderRadius: 14, padding: '20px 18px', width: '100%', textAlign: 'center',
                position: 'relative', overflow: 'hidden',
              }}>
                {/* Progress fill */}
                <div style={{
                  position: 'absolute', bottom: 0, left: 0, right: 0,
                  height: `${barHeight}%`, background: `${step.color}08`,
                }} />

                <div style={{fontFamily: FONT, fontSize: 17, fontWeight: 700, color: C.white, marginBottom: 8, zIndex: 1, position: 'relative'}}>
                  {step.title}
                </div>
                <div style={{fontFamily: FONT, fontSize: 13, color: C.gray, lineHeight: 1.5, marginBottom: 12, zIndex: 1, position: 'relative'}}>
                  {step.detail}
                </div>
                <div style={{
                  fontFamily: MONO, fontSize: 11, color: step.color, background: `${step.color}10`,
                  borderRadius: 6, padding: '6px 10px', zIndex: 1, position: 'relative',
                }}>{step.cmd}</div>
              </div>

              {/* Arrow connector */}
              {i < steps.length - 1 && (
                <div style={{
                  position: 'absolute', right: -14, top: '50%',
                  fontFamily: MONO, fontSize: 20, color: C.gray,
                  opacity: interpolate(frame, [d + 15, d + 20], [0, 0.5], {
                    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
                  }),
                }}>→</div>
              )}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/* ── SCENE 8: Automation / How CLI automates (62-72s) ── */
const SceneAutomation = () => {
  const frame = useCurrentFrame();

  const automationSteps = [
    {icon: '⏰', label: 'Daily CRON at 09:00 UTC', detail: 'OpenClaw triggers nansenscope daily', delay: 10},
    {icon: '🔍', label: 'Auto-scan 5 chains', detail: '20+ API calls via x402 micropayments', delay: 20},
    {icon: '📊', label: 'Generate report + charts', detail: 'Markdown + interactive HTML dashboard', delay: 30},
    {icon: '🚨', label: 'Alert on high-conviction signals', detail: 'Discord notification if score > threshold', delay: 40},
    {icon: '🔄', label: 'Compare with yesterday', detail: 'Track new entries, exits, position changes', delay: 50},
    {icon: '📱', label: 'Deliver to your channel', detail: 'Morning brief ready when you wake up', delay: 60},
  ];

  return (
    <AbsoluteFill style={{display: 'flex', alignItems: 'center', padding: '0 80px'}}>
      <div style={{flex: '0 0 38%', paddingRight: 50}}>
        <FadeIn delay={0} direction="right">
          <Badge text="Zero Manual Work" glow />
        </FadeIn>
        <div style={{margin: '18px 0'}}>
          <WordReveal text="Runs while you sleep" delay={8} interval={5} fontSize={50} highlight="sleep" />
        </div>
        <FadeIn delay={18}>
          <div style={{
            fontFamily: MONO, fontSize: 14, color: C.gray, marginTop: 16,
            background: 'rgba(13,17,23,0.8)', border: `1px solid ${C.tealBorder}`,
            borderRadius: 10, padding: '14px 16px', lineHeight: 1.8,
          }}>
            <div><span style={{color: C.teal}}>$</span> openclaw cron add \</div>
            <div>&nbsp;&nbsp;--schedule "0 9 * * *" \</div>
            <div>&nbsp;&nbsp;--task "nansenscope daily"</div>
            <div style={{marginTop: 8, color: C.teal}}>Cron created. Next run: 09:00 UTC</div>
          </div>
        </FadeIn>
        <FadeIn delay={50}>
          <p style={{fontFamily: FONT, fontSize: 18, color: C.gray, marginTop: 16, lineHeight: 1.6}}>
            One command to set up. Runs forever. Costs ~$0.20/day.
          </p>
        </FadeIn>
      </div>

      <div style={{flex: '0 0 62%'}}>
        <div style={{display: 'flex', flexDirection: 'column', gap: 10}}>
          {automationSteps.map((step, i) => {
            const d = step.delay;
            const opacity = interpolate(frame, [d, d + 8], [0, 1], {
              extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
            });
            const slideX = interpolate(frame, [d, d + 10], [30, 0], {
              extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
            });
            const checkOpacity = interpolate(frame, [d + 12, d + 16], [0, 1], {
              extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
            });
            const lineProgress = interpolate(frame, [d + 5, d + 15], [0, 100], {
              extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
            });

            return (
              <div key={i} style={{
                opacity, transform: `translateX(${slideX}px)`,
                display: 'flex', alignItems: 'center', gap: 14,
                background: 'rgba(13,17,23,0.7)', border: `1px solid ${C.tealBorder}`,
                borderRadius: 10, padding: '14px 18px',
                position: 'relative', overflow: 'hidden',
              }}>
                {/* Progress line */}
                <div style={{
                  position: 'absolute', left: 0, top: 0, bottom: 0,
                  width: `${lineProgress}%`, background: C.tealDim, borderRadius: 10,
                }} />

                <span style={{fontSize: 22, zIndex: 1}}>{step.icon}</span>
                <div style={{flex: 1, zIndex: 1}}>
                  <span style={{fontFamily: FONT, fontSize: 17, fontWeight: 700, color: C.white}}>{step.label}</span>
                  <div style={{fontFamily: FONT, fontSize: 13, color: C.gray, marginTop: 2}}>{step.detail}</div>
                </div>
                <span style={{
                  fontFamily: MONO, fontSize: 18, color: C.teal, opacity: checkOpacity, zIndex: 1,
                }}>✓</span>

                {/* Connector line to next step */}
                {i < automationSteps.length - 1 && (
                  <div style={{
                    position: 'absolute', left: 30, bottom: -10, width: 2, height: 10,
                    background: C.tealBorder,
                    opacity: interpolate(frame, [d + 10, d + 14], [0, 0.5], {
                      extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
                    }),
                  }} />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ── SCENE 9: How We Built This ── */
const SceneRecap = () => {
  const frame = useCurrentFrame();
  const items = [
    {icon: '>', label: 'OpenClaw Agent Fleet', detail: 'Orchestrated by Claw across Discord'},
    {icon: '>', label: 'Daily CRON Jobs', detail: 'Automated scans, reports, alerts'},
    {icon: '>', label: '18 CLI Commands', detail: 'scan, perps, exit-signals, defi, search...'},
    {icon: '>', label: 'Multi-Chain Analysis', detail: 'Ethereum, Base, Solana, Arbitrum, Polygon'},
    {icon: '>', label: 'Landing Page + Dashboard', detail: 'Interactive results viewer with charts'},
    {icon: '>', label: 'OpenClaw Skill', detail: 'Installable by anyone, plug and play'},
    {icon: '>', label: 'Remotion Video', detail: 'This video -- vibe coded by the agent'},
    {icon: '>', label: '#NansenCLI Week 2', detail: '7 days of building, shipping, iterating'},
  ];

  return (
    <AbsoluteFill style={{display: 'flex', padding: '0 80px', alignItems: 'center'}}>
      <div style={{flex: '0 0 35%', paddingRight: 40}}>
        <FadeIn delay={0} direction="right">
          <Badge text="Build Log" glow />
        </FadeIn>
        <div style={{margin: '18px 0'}}>
          <WordReveal text="How we built this" delay={8} interval={5} fontSize={50} highlight="built" />
        </div>
        <FadeIn delay={16}>
          <p style={{fontFamily: FONT, fontSize: 20, color: C.gray, lineHeight: 1.6}}>
            One operator. One AI fleet.<br/>
            7 days. Zero manual coding.
          </p>
        </FadeIn>
        <FadeIn delay={28}>
          <div style={{
            marginTop: 20, fontFamily: MONO, fontSize: 15, color: C.teal,
            background: C.tealDim, border: `1px solid ${C.tealBorder}`,
            borderRadius: 10, padding: '14px 18px',
          }}>
            Powered by OpenClaw + Claude Opus
          </div>
        </FadeIn>
      </div>
      <div style={{flex: '0 0 65%'}}>
        <div style={{display: 'flex', flexDirection: 'column', gap: 10}}>
          {items.map((item, i) => {
            const d = 10 + i * 10;
            const opacity = interpolate(frame, [d, d + 8], [0, 1], {
              extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
            });
            const slideX = interpolate(frame, [d, d + 10], [40, 0], {
              extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
            });
            const barWidth = interpolate(frame, [d + 5, d + 18], [0, 100], {
              extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
            });
            return (
              <div key={i} style={{
                opacity, transform: `translateX(${slideX}px)`,
                display: 'flex', alignItems: 'center', gap: 14,
                background: 'rgba(13,17,23,0.7)', border: `1px solid ${C.tealBorder}`,
                borderRadius: 10, padding: '12px 18px',
                position: 'relative', overflow: 'hidden',
              }}>
                {/* Progress fill */}
                <div style={{
                  position: 'absolute', left: 0, top: 0, bottom: 0,
                  width: `${barWidth}%`, background: C.tealDim,
                  borderRadius: 10,
                }} />
                <span style={{fontFamily: MONO, fontSize: 16, color: C.teal, zIndex: 1}}>{item.icon}</span>
                <span style={{fontFamily: FONT, fontSize: 18, fontWeight: 700, color: C.white, zIndex: 1}}>{item.label}</span>
                <span style={{fontFamily: FONT, fontSize: 15, color: C.gray, marginLeft: 'auto', zIndex: 1}}>{item.detail}</span>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ── SCENE 8: CTA / Outro (62-72s) ── */
const SceneOutro = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const scale = spring({frame, fps, from: 0.7, to: 1, durationInFrames: 30, config: {damping: 10}});
  const lineWidth = interpolate(frame, [20, 55], [0, 600], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const rotation = interpolate(frame, [0, 360], [0, 360], {extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      {/* Background rings */}
      {[200, 350, 500].map((size, i) => (
        <div key={i} style={{
          position: 'absolute', width: size, height: size, borderRadius: '50%',
          border: `1px solid rgba(0,229,160,${0.08 + i * 0.04})`,
          transform: `rotate(${rotation * (i % 2 === 0 ? 1 : -1) * 0.3}deg)`,
        }} />
      ))}

      <div style={{textAlign: 'center', transform: `scale(${scale})`, zIndex: 10}}>
        <div style={{marginBottom: 8}}>
          <WordReveal text="Detect · Verify · Monitor" delay={5} interval={8} fontSize={84} highlight="Monitor" />
        </div>
        <div style={{
          width: lineWidth, height: 3,
          background: `linear-gradient(90deg, transparent, ${C.teal}, transparent)`,
          margin: '28px auto',
          boxShadow: `0 0 20px ${C.tealGlow}`,
        }} />
        <FadeIn delay={15}>
          <p style={{fontFamily: MONO, fontSize: 26, color: C.teal, margin: '0 0 10px'}}>
            github.com/Luigi08001/nansenscope
          </p>
        </FadeIn>
        <FadeIn delay={25}>
          <p style={{fontFamily: FONT, fontSize: 22, color: C.gray}}>
            Built for #NansenCLI Challenge Week 2
          </p>
        </FadeIn>
        <FadeIn delay={38}>
          <div style={{marginTop: 28, display: 'flex', gap: 14, justifyContent: 'center'}}>
            <Badge text="OpenClaw Skill" glow />
            <Badge text="Open Source" glow />
            <Badge text="Vibe Coded" glow />
          </div>
        </FadeIn>
      </div>
    </AbsoluteFill>
  );
};

/* ── Scene transition wrapper ── */
const SceneTransition = ({children}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const fadeIn = interpolate(frame, [0, 12], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const fadeOut = interpolate(frame, [durationInFrames - 12, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const scaleIn = interpolate(frame, [0, 12], [0.97, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill style={{opacity: fadeIn * fadeOut, transform: `scale(${scaleIn})`}}>
      {children}
    </AbsoluteFill>
  );
};

/* ── Main composition ── */
export const NansenScopeDemo = () => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();

  const scenes = [
    {start: 0, dur: 4, Comp: SceneIntro},           // Hook
    {start: 4, dur: 4, Comp: SceneProblem},          // Pain point
    {start: 8, dur: 7, Comp: SceneSolution},         // Landing page
    {start: 15, dur: 8, Comp: SceneTerminalScan},    // Scan 5 chains
    {start: 23, dur: 9, Comp: SceneTerminalMore},    // Perps, exits, search, defi
    {start: 32, dur: 8, Comp: SceneDashboard},       // Results viewer
    {start: 40, dur: 8, Comp: SceneSignalToAction},  // Detect>Verify>Act>Monitor
    {start: 48, dur: 10, Comp: SceneAutomation},     // CRON + automation flow
    {start: 58, dur: 8, Comp: SceneCharts},          // Stats + charts
    {start: 66, dur: 10, Comp: SceneRecap},          // Build log
    {start: 76, dur: 9, Comp: SceneOutro},           // CTA
  ];

  return (
    <AbsoluteFill style={{background: C.bg}}>
      <AnimatedBg frame={frame} />
      <VibeBadge />
      {/* Background music - lowered */}
      <Audio src={staticFile('bgmusic.mp3')} volume={0.08} />

      {/* Voiceover segments synced to scenes */}
      <Sequence from={0 * fps} durationInFrames={4 * fps}>
        <Audio src={staticFile('vo_intro.m4a')} volume={1} />
      </Sequence>
      <Sequence from={8 * fps} durationInFrames={7 * fps}>
        <Audio src={staticFile('vo_solution.m4a')} volume={1} />
      </Sequence>
      <Sequence from={15 * fps} durationInFrames={8 * fps}>
        <Audio src={staticFile('vo_scan.m4a')} volume={1} />
      </Sequence>
      <Sequence from={23 * fps} durationInFrames={9 * fps}>
        <Audio src={staticFile('vo_more.m4a')} volume={1} />
      </Sequence>
      <Sequence from={32 * fps} durationInFrames={8 * fps}>
        <Audio src={staticFile('vo_dash.m4a')} volume={1} />
      </Sequence>
      <Sequence from={40 * fps} durationInFrames={8 * fps}>
        <Audio src={staticFile('vo_signal.m4a')} volume={1} />
      </Sequence>
      <Sequence from={48 * fps} durationInFrames={10 * fps}>
        <Audio src={staticFile('vo_auto.m4a')} volume={1} />
      </Sequence>
      <Sequence from={58 * fps} durationInFrames={8 * fps}>
        <Audio src={staticFile('vo_charts.m4a')} volume={1} />
      </Sequence>
      <Sequence from={66 * fps} durationInFrames={10 * fps}>
        <Audio src={staticFile('vo_build.m4a')} volume={1} />
      </Sequence>
      <Sequence from={76 * fps} durationInFrames={9 * fps}>
        <Audio src={staticFile('vo_outro.m4a')} volume={1} />
      </Sequence>
      {scenes.map(({start, dur, Comp}, i) => (
        <Sequence key={i} from={start * fps} durationInFrames={(dur + 0.5) * fps}>
          <SceneTransition>
            <Comp />
          </SceneTransition>
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
