import React from 'react';
import {registerRoot, Composition} from 'remotion';
import {NansenScopeProduct} from './Root.jsx';

const RemotionRoot = () => {
  return (
    <Composition
      id="NansenScopeProduct"
      component={NansenScopeProduct}
      durationInFrames={45 * 24}
      fps={24}
      width={1920}
      height={1080}
    />
  );
};

registerRoot(RemotionRoot);
