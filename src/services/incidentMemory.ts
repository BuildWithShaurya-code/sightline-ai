import type {PaginatedIncidentsResponse} from './api.ts';
import type {Incident} from '../types/sightline.ts';

/** Short-lived display data only. Never persisted, and never used as authorization. */
export class IncidentMemory {
  private owner:string|null=null;
  private revision=0;
  private pages=new Map<string,{value:PaginatedIncidentsResponse;expires:number}>();
  private rows=new Map<string,{value:Incident;expires:number}>();
  constructor(private ttl=30000,private now=()=>Date.now()){}
  clear(){this.rows.clear();this.pages.clear();this.owner=null;this.revision++;}
  private bind(owner:string|null){if(owner!==this.owner){this.clear();this.owner=owner;}}
  ticket(owner:string|null){this.bind(owner);return this.revision;}
  get(owner:string|null,id:string):Incident|null {
    this.bind(owner);const row=this.rows.get(id);
    if(!owner||!row)return null;
    if(row.expires<=this.now()){this.rows.delete(id);return null;}
    return structuredClone(row.value);
  }
  put(owner:string|null,ticket:number,value:Incident){
    if(!owner||owner!==this.owner||ticket!==this.revision)return;
    this.rows.delete(value.id);
    this.rows.set(value.id,{value:structuredClone(value),expires:this.now()+this.ttl});
    while(this.rows.size>20)this.rows.delete(this.rows.keys().next().value!);
  }
  page(owner:string|null,key:string):PaginatedIncidentsResponse|null {
    this.bind(owner);const row=this.pages.get(key);
    if(!owner||!row)return null;
    if(row.expires<=this.now()){this.pages.delete(key);return null;}
    return structuredClone(row.value);
  }
  putPage(owner:string|null,ticket:number,key:string,value:PaginatedIncidentsResponse){
    if(!owner||owner!==this.owner||ticket!==this.revision)return;
    this.pages.delete(key);this.pages.set(key,{value:structuredClone(value),expires:this.now()+this.ttl});
    while(this.pages.size>10)this.pages.delete(this.pages.keys().next().value!);
  }
  invalidate(owner:string|null,id:string){this.bind(owner);this.rows.delete(id);this.pages.clear();this.revision++;}
}
export const incidentMemory=new IncidentMemory();
