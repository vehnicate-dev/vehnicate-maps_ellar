import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = "https://mmjusghgeedycrrfdejg.supabase.co";
const SUPABASE_ANON_KEY = "sb_publishable_unNgZxi4yyID9qAAy3d2dg_dGJLpv3N";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);