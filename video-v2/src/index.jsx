import React from 'react';
import {registerRoot, Composition} from 'remotion';
import {NansenScopeDemo} from './Root.jsx';

const RemotionRoot = () => {
  return (
    <Composition
      id="NansenScopeDemo"
      component={NansenScopeDemo}
      durationInFrames={85 * 30}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};

registerRoot(RemotionRoot);
