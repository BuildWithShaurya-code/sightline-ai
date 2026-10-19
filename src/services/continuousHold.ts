/** Requires one uninterrupted hold; repeats and multiple timers cannot complete it twice. */
export class ContinuousHold {
  private started: number|null = null;
  constructor(readonly durationMs=3000) {}
  start(now: number) { if(this.started===null)this.started=now; }
  cancel() {this.started=null;}
  advance(now: number) {
    if(this.started===null)return {progress:0,complete:false};
    const progress=Math.max(0,Math.min(1,(now-this.started)/this.durationMs));
    if(progress>=1){this.started=null;return {progress:1,complete:true};}
    return {progress,complete:false};
  }
}
