import { createClient } from "@supabase/supabase-js";

//main db:
//const SUPABASE_URL = "https://mmjusghgeedycrrfdejg.supabase.co";
//const SUPABASE_ANON_KEY = "sb_publishable_unNgZxi4yyID9qAAy3d2dg_dGJLpv3N";

//test db:
const SUPABASE_URL = "https://jypgvhydqgwycqngqjpw.supabase.co";
const SUPABASE_ANON_KEY = "sb_publishable_-s_SaqTijeKr8UEM3X9LOA_XRIRHlTD";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);