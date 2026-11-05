import { http } from "@/utils/http";
export type Competition = { id:number; name:string; created_at:string };
export type Batch = { id:number; name:string; status:string; current_version:number; competition:number; competition_name:string };
export const listCompetitions=()=>http.get<Competition[],never>("/api/v1/competitions/");
export const createCompetition=(data:object)=>http.post<Competition,object>("/api/v1/competitions/",{data});
export const listBatches=()=>http.get<Batch[],never>("/api/v1/batches/");
export const createBatch=(data:object)=>http.post<Batch,object>("/api/v1/batches/",{data});
