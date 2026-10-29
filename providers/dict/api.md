
# request of translations + inflections
# the word must be clean lemma not inflected
lang: DE-EN
GET https://www.dict.cc/syn/app_translations.php?s=Warum&dir=1&lp=DEEN&appversioncode=260804

Accept:*/*

Accept-Encoding:gzip, deflate, br, zstd

Accept-Language:en-GB,en-US;q=0.9,en;q=0.8

Connection:keep-alive

Host:www.dict.cc


# request of translations + inflections
# the word must be clean lemma not inflected
lang: EN-NO
GET https://www.dict.cc/syn/app_translations.php?s=kalv&dir=2&lp=ENNO&appversioncode=260804


# response

```
{

"translations": [

{

"id": 528676,

"term1": "calf",

"term2": "kalv {m}",

"entry_type": "noun",

"subj_ids": ",25,",

"vt_usage": 0,

"sort_num": 16

}

],

"dir": 2,

"inflections": "<tr title=\"article indefinite.sg | definite.sg | indefinite.pl | definite.pl\"><td valign=\"top\"></td><td valign=\"top\"><b>NOUN</b>&nbsp;&nbsp;</td><td width=\"95%\" > en&nbsp;kalv <span class=\"infl_pipe\">|</span> kalven <span class=\"infl_pipe\">|</span> kalver <span class=\"infl_pipe\">|</span> kalvene </td></tr>",

"inflections_repl": " en&nbsp;kalv \tkalv\t;\t kalven \tkalven\t;\t kalver \tkalver\t;\t kalvene \tkalvene\t;\t",

"inflections_info": "<br><b>NOUN</b> &nbsp; article indefinite.sg | definite.sg | indefinite.pl | definite.pl"

}
```


# Recordings (tts)
GET https://audio.dict.cc/speak.audio.v2.php?error_as_text=1&type=mp3&id=528676&lang=NO_rec_ip&lp=ENNO&appversioncode=260804&text=kalv (human)

GET https://audio.dict.cc/speak.audio.v2.php?error_as_text=1&type=mp3&id=1335801&lang=rec&lp=ENNO&appversioncode=260804 (human the same as previous)

GET https://audio.dict.cc/speak.audio.v2.php?error_as_text=1&type=mp3&id=528676&lang=NO&lp=ENNO&appversioncode=260804&voice=Liv (robot)