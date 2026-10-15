import React from 'react';
import {Composition} from 'remotion';
import {Demo, total} from './Demo';
export const RemotionRoot: React.FC = () => (<>
  <Composition id="Demo" component={Demo} durationInFrames={total} fps={30} width={1920} height={1080} defaultProps={{vertical: false}} />
  <Composition id="Vertical" component={Demo} durationInFrames={total} fps={30} width={1080} height={1920} defaultProps={{vertical: true}} />
</>);
