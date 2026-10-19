/** One pointer gesture; taps open confirmation and short drags cancel. */
export class SlideGesture {
  private active:{pointer:number;start:number;travel:number;initial:number;furthest:number}|null=null;
  progress=0;
  start(pointer:number,x:number,travel:number){
    if(this.active)return false;
    this.active={pointer,start:x,travel:Math.max(1,travel),initial:this.progress,furthest:0};return true;
  }
  move(pointer:number,x:number){
    const gesture=this.active;if(!gesture||gesture.pointer!==pointer)return false;
    gesture.furthest=Math.max(gesture.furthest,Math.abs(x-gesture.start));
    this.progress=Math.max(0,Math.min(1,gesture.initial+(x-gesture.start)/gesture.travel));return true;
  }
  finish(pointer:number,x:number):'tap'|'complete'|'cancel'|null{
    if(!this.move(pointer,x))return null;
    const tap=this.active!.furthest<=8;
    this.active=null;
    const result=tap?'tap':this.progress>=.85?'complete':'cancel';
    this.progress=0;return result;
  }
  cancel(){this.active=null;this.progress=0;}
  step(delta:number){this.progress=Math.max(0,Math.min(1,this.progress+delta));return this.progress>=.85;}
}
