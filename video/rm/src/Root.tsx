import React from 'react';
import {Composition} from 'remotion';
import {Demo, total} from './Demo';
import {DemoV2, totalV2} from './v2/DemoV2';
export const RemotionRoot: React.FC = () => (<>
  <Composition id="Demo" component={Demo} durationInFrames={total} fps={30} width={1920} height={1080} defaultProps={{vertical: false}} />
  <Composition id="Vertical" component={Demo} durationInFrames={total} fps={30} width={1080} height={1920} defaultProps={{vertical: true}} />
  <Composition id="DemoV2" component={DemoV2} durationInFrames={totalV2} fps={30} width={1920} height={1080} />
</>);
