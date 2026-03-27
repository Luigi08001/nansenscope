import React from 'react';
import {AbsoluteFill, Audio, Img, Sequence, Video, staticFile, useVideoConfig, interpolate, useCurrentFrame} from 'remotion';

const OverlayText = ({text, sub, color = '#00E5A0'}) => {
  const f = useCurrentFrame();
  const opacity = interpolate(f, [0, 10, 80, 95], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', padding: 60, opacity}}>
      <div style={{display: 'inline-block', background: 'rgba(6,11,20,0.72)', border: '1px solid rgba(0,229,160,0.25)', borderRadius: 12, padding: '14px 20px'}}>
        <div style={{fontFamily: 'Inter, sans-serif', color, fontSize: 40, fontWeight: 700, lineHeight: 1.1}}>{text}</div>
        {sub ? <div style={{fontFamily: 'Inter, sans-serif', color: '#E8ECF2', fontSize: 24, marginTop: 6}}>{sub}</div> : null}
      </div>
    </AbsoluteFill>
  );
};

const VibeBadge = () => {
  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'flex-end', padding: 24}}>
      <div style={{fontFamily: 'JetBrains Mono, monospace', fontSize: 18, color: '#00E5A0', background: 'rgba(6,11,20,0.8)', border: '1px solid rgba(0,229,160,0.35)', borderRadius: 8, padding: '8px 12px'}}>
        VIBE CODED • built by Op-Claw automation
      </div>
    </AbsoluteFill>
  );
};

export const NansenScopeProduct = () => {
  const {fps} = useVideoConfig();
  const intro = 3 * fps;
  const main = 39 * fps;
  const outro = 3 * fps;

  return (
    <AbsoluteFill style={{backgroundColor: '#060B14'}}>
      <Audio src={staticFile('voiceover_live.m4a')} volume={0.95} />

      <Sequence from={0} durationInFrames={intro}>
        <Img src={staticFile('intro_live.png')} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      </Sequence>

      <Sequence from={intro} durationInFrames={main}>
        <AbsoluteFill>
          <Video src={staticFile('raw_live.mov')} startFrom={0} endAt={main} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
          <VibeBadge />
          <Sequence from={1 * fps} durationInFrames={3 * fps}><OverlayText text="Real Live Product Demo" sub="NansenScope in action" /></Sequence>
          <Sequence from={10 * fps} durationInFrames={3 * fps}><OverlayText text="Scan smart money across chains" sub="Find high-conviction signals first" /></Sequence>
          <Sequence from={22 * fps} durationInFrames={3 * fps}><OverlayText text="Perps + Exit Signals" sub="Momentum and risk in one flow" /></Sequence>
          <Sequence from={31 * fps} durationInFrames={3 * fps}><OverlayText text="Detect · Verify · Monitor" sub="Execution-ready intelligence loop" /></Sequence>
        </AbsoluteFill>
      </Sequence>

      <Sequence from={intro + main} durationInFrames={outro}>
        <Img src={staticFile('outro_live.png')} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      </Sequence>
    </AbsoluteFill>
  );
};
