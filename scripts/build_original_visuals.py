"""Reproduce 100 original subject illustrations (MIT). No downloaded artwork."""
from pathlib import Path
import html
import json
import copy
import hashlib
import io
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1] / 'zhijiang/assets/visuals'

def p(d, fill='none', stroke=None):
    return f'<path d="{d}" fill="{fill}"'+(f' stroke="{stroke}"' if stroke else '')+'/>'
def c(x,y,r,fill='none'):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"/>'
def r(x,y,w,h,fill='none',rx=12):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"/>'
G='#8BBC79'; Y='#F2CC68'; B='#8BB9CF'; R='#D97C72'; W='#FFF5DB'; INK='#35463E'

# Curves, silhouettes and details are individually authored. The shared stroke
# treatment does not invent domain relations or anatomical measurements.
D = {
'watermelon': p('M95 245 C48 92 339 75 378 209 C413 362 129 412 95 245Z',G)+p('M163 127 Q116 241 188 349 M225 112 Q180 246 248 360 M291 127 Q251 245 310 334',stroke='#43704A')+p('M290 124 Q276 75 319 87'),
'watermelon-slice': p('M65 168 Q236 418 412 171 L65 168Z',G)+p('M84 169 Q239 372 390 171Z',W)+p('M105 172 Q240 336 369 174Z',R)+''.join(p(f'M{x} {y} q-12 15 0 23 q12-10 0-23Z',INK) for x,y in [(162,205),(239,250),(313,206)]),
'melon-seedling': p('M240 366 Q257 277 237 207 M239 254 Q169 257 136 200 Q220 187 239 254Z',G)+p('M240 211 Q237 134 314 140 Q318 204 240 211Z',G)+p('M124 366 Q239 392 349 365')+p('M236 366 l-23 34 M244 371 l30 29'),
'leaf': p('M105 347 Q105 129 369 94 Q399 332 105 347Z',G)+p('M95 367 L326 137 M176 286 l-19-67 M230 230 l66 9 M275 184 l-4-54'),
'apple': p('M236 147 C102 71 70 219 118 310 C167 398 218 349 238 350 C295 389 383 326 379 222 C374 108 287 107 236 147Z',R)+p('M236 147 Q231 83 260 68')+p('M252 106 Q271 51 326 85 Q293 120 252 106Z',G)+p('M143 183 Q113 223 139 275',stroke=W),
'wheat': p('M245 407 L245 102')+''.join(p(f'M245 {y} Q{a} {y-70} {a} {y-22} Q{a} {y+9} 245 {y+24}Z',Y) for y,a in [(130,195),(175,294),(222,184),(270,303),(314,193)]),
'soil': p('M66 219 Q143 241 216 219 Q294 197 416 219 L416 383 L66 383Z','#B99472')+p('M83 277 l41 12 M176 337 l45-12 M284 272 l29 13 M340 352 l46-9')+p('M239 222 L239 131 M239 158 Q170 142 177 106 Q229 103 239 158Z',G)+p('M239 133 Q273 74 311 107 Q299 145 239 133Z',G),
'watering-can': r(89,194,181,164,B)+p('M270 233 L368 164 L391 189 L281 302Z',B)+p('M91 222 Q20 186 40 301 Q52 338 91 300')+p('M158 194 L166 148 L218 152 L222 194',B)+''.join(p(f'M{x} {y} l-9 25',stroke=B) for x,y in [(369,224),(399,233),(422,212)]),
'sun': c(240,240,89,Y)+''.join(p(d) for d in ['M240 50v51','M240 380v49','M52 240h50','M378 240h49','M102 102l38 38','M342 342l37 37','M102 379l39-39','M340 140l40-40']),
'book': p('M240 136 Q137 78 62 126 L65 363 Q165 316 240 365 Q324 317 420 360 L418 122 Q318 77 240 136Z',W)+p('M240 136v229 M96 166q73-23 109 4 M96 223q73-23 109 4 M278 167q61-27 105 0 M278 224q61-27 105 0'),
'laptop': r(99,96,287,224,B)+r(120,118,244,177,W)+p('M99 320 L49 375 Q242 408 432 375 L386 320Z',B)+p('M202 349h78'),
'chip': r(136,136,208,208,G)+r(181,181,118,118,W)+''.join(p(f'M{x} 104v32 M{x} 344v33 M104 {x}h32 M344 {x}h33') for x in [170,216,264,312]),
'network': ''.join(p(d) for d in ['M116 113l124 127','M116 367l124-127','M240 240l127-129','M240 240l127 127','M116 113v254','M367 111v256'])+''.join(c(x,y,31,B if x==240 else G) for x,y in [(116,113),(116,367),(240,240),(367,111),(367,367)]),
'database': r(107,136,266,223,B)+p('M107 137 C106 60 375 59 373 137 C373 213 107 208 107 137Z',W)+p('M108 215c3 76 263 74 264 0 M108 288c3 76 263 74 264 0'),
'robot': r(103,126,279,237,B)+c(177,222,24,W)+c(307,222,24,W)+p('M175 301q68 26 133-1 M240 126V79')+c(240,64,18,R)+r(59,189,41,95,Y)+r(386,189,40,95,Y),
'magnifier': c(207,200,112,W)+p('M285 282l105 106',B)+p('M154 205l36 34 70-78',stroke=G),
'decision-tree': p('M240 123v76 M118 199h244 M118 199v84 M362 199v84')+r(181,52,118,77,Y)+r(66,281,105,85,G)+r(308,281,107,85,B),
'cloud': p('M122 312 C35 303 40 187 126 181 C127 64 300 73 304 173 C398 118 470 270 377 310Z',B)+p('M239 360V215 M197 256l42-41 42 41'),
'shield': p('M92 115 L240 65 L389 115 Q405 330 240 416 Q74 327 92 115Z',G)+p('M160 231l57 57 109-122',stroke=W),
'data-table': r(64,103,351,274,W)+p('M65 176h349 M65 246h349 M65 313h349 M181 103v274 M298 103v274')+r(83,118,82,39,Y)+r(201,190,78,39,G)+r(318,329,75,31,B),
'compass': c(240,89,25,Y)+p('M229 115L117 392 M250 114L366 392 M169 269h148 M128 366q112 61 222 0')+p('M114 392l-7 32 M366 392l10 33'),
'ruler': p('M64 301 L330 79 L401 165 L136 388Z',Y)+''.join(p(f'M{x} {y} l24 29') for x,y in [(111,261),(151,228),(191,195),(232,161),(272,129)]),
'abacus': r(69,83,342,315,W)+''.join(p(f'M90 {y}h302')+''.join(c(x,y,21,col) for x,col in [(137,G),(187,G),(292,R),(340,R)]) for y in [145,219,293,359]),
'dice': r(96,96,291,291,W,40)+''.join(c(x,y,21,INK) for x,y in [(154,152),(326,151),(240,240),(153,326),(326,326)]),
'coordinate-plane': p('M63 347H411 M140 420V66 M391 334l20 13-20 13 M127 86l13-20 13 20')+p('M143 320 Q260 291 336 118',stroke=R)+c(247,254,13,Y),
'geometry-shapes': p('M83 305L186 99L289 305Z',G)+c(336,171,68,B)+r(269,290,136,117,Y),
'balance': p('M240 99v303 M86 157h306 M86 157L45 263h82Z',B)+p('M392 157l-41 106h82Z',Y)+p('M130 409h220 M74 287q14 13 27 0 M379 287q14 13 27 0'),
'fraction-pie': c(240,240,163,W)+p('M240 240L240 78 A162 162 0 0 1 402 240Z',R)+p('M240 78v324 M78 240h324'),
'light-bulb': p('M183 328 C175 271 90 237 125 145 C172 34 327 72 360 161 C387 246 314 272 296 328Z',Y)+p('M183 330h114 M190 358h100 M204 386h72 M216 327l-22-124 46 33 43-33-20 124'),
'battery': r(86,150,301,181,G)+r(387,206,34,69,Y)+p('M130 240h64 M162 208v64 M276 240h65'),
'magnet': p('M110 94v194 C110 428 374 430 374 288V94 H289v194 C289 340 197 343 197 288V94Z',R)+r(110,94,87,71,B)+r(289,94,85,71,B),
'spring': p('M107 84h266 M109 394h264 M240 84v36 l-69 27 137 34-138 34 139 35-139 32 138 35-67 25v36',stroke=B),
'pendulum': p('M81 82h319 M240 82L357 329')+c(357,329,43,Y)+p('M90 309Q238 410 375 312',stroke=B)+p('M240 99v206'),
'wave': p('M57 239 C105 52 163 52 211 239 S314 430 365 239 S410 111 440 134',stroke=B)+p('M62 373H422'),
'prism': p('M154 369L271 116L398 369Z',B)+p('M45 156L202 264',stroke=Y)+p('M307 200L446 175',stroke=R)+p('M316 221L446 224',stroke=G)+p('M326 243L446 272',stroke=B),
'gear': p('M204 71h72l11 43 36 20 43-12 36 62-32 31v49l33 32-37 62-43-12-36 20-12 43h-72l-12-43-36-20-43 12-36-62 33-32v-49l-33-31 37-62 42 12 37-20Z',B)+c(240,240,67,W),
'circuit': p('M70 115h147 M287 115h126v251H70V115 M70 236h94 M312 236h101')+r(164,209,148,52,Y)+p('M218 88v55 M244 62v108 M286 87v58'),
'thermometer': p('M207 307 V99 C207 52 275 52 275 99V307 A67 67 0 1 1 207 307Z',W)+p('M240 307V174',stroke=R)+c(240,355,34,R)+p('M291 134h47 M291 192h31 M291 249h47'),
'flask': p('M190 73h104 M201 75v137L100 369Q92 405 131 405H357Q397 405 380 369L284 212V75',W)+p('M146 298Q242 318 336 298L380 369Q396 405 357 405H131Q94 405 100 369Z',B)+c(210,332,12,W)+c(277,365,18,W),
'test-tubes': ''.join(p(f'M{x} 91v247q35 85 70 0V91 M{x-9} 91h88',W)+p(f'M{x+2} 246v92q33 74 66 0v-92Z',color) for x,color in [(106,G),(293,R)]),
'molecule': p('M240 238L123 120 M240 238l128-127 M240 238l111 134 M240 238L116 372')+c(240,238,58,B)+''.join(c(x,y,35,col) for x,y,col in [(123,120,R),(368,111,G),(351,372,Y),(116,372,W)]),
'atom': c(240,240,25,R)+''.join(f'<ellipse cx="240" cy="240" rx="174" ry="66" transform="rotate({angle} 240 240)" fill="none"/>' for angle in [0,60,120])+c(413,240,16,B)+c(153,86,16,G),
'drop': p('M240 67 Q193 149 124 246 C35 423 444 435 359 249 Q293 149 240 67Z',B)+p('M149 289q-14 53 40 78',stroke=W),
'crystal': p('M115 158L241 68L372 158L331 345L239 411L149 345Z',B)+p('M115 158h257 M241 68l-48 91 47 251 46-251-45-91 M149 345l44-186 M331 345l-45-186'),
'pipette': p('M300 69l70 63-225 251-59 32 27-67Z',B)+p('M287 83l67 65 M219 155l62 56')+p('M79 426q-25 40 0 41q24 0 0-41Z',B),
'beaker': p('M103 91h270 M122 91v299q120 39 240 0V91',W)+p('M123 250q120 21 238 0v140q-120 38-238 0Z',G)+p('M291 151h48 M310 203h29 M291 303h48'),
'dna': p('M139 61C396 149 91 319 343 422 M341 61C85 149 390 319 139 422',stroke=B)+''.join(p(d,stroke=G) for d in ['M139 61h202','M206 105h66','M205 181h73','M142 239h196','M206 303h70','M206 375h67','M140 422h201']),
'cell': p('M109 133 C235 39 414 117 399 257 C394 411 221 440 113 348 C45 295 41 193 109 133Z',G)+c(257,248,70,R)+c(274,233,20,W)+p('M142 181q65-60 63 12q-12 51-63-12Z',Y)+p('M306 346q65-60 63 12q-12 51-63-12Z',Y),
'microscope': p('M81 405h324 M281 405v-94 M112 287h165 M239 108l-76 131 65 41 78-131Z',B)+p('M270 138Q399 147 365 278Q346 339 282 340')+c(298,269,29,Y)+p('M222 84l49 27 M154 252l60 35'),
'butterfly': p('M239 222C49 6 23 160 167 268 C33 338 139 474 239 277 C350 474 449 333 314 267 C463 147 421 6 239 222Z',Y)+p('M240 190v137 M240 190l-34-61 M240 190l35-61')+c(135,178,28,R)+c(341,178,28,R),
'fish': p('M99 240Q235 57 363 240Q235 413 99 240Z',B)+p('M363 240l73-81v159Z',G)+c(152,227,13,INK)+p('M235 205l54 34-54 32Z',Y),
'tree': p('M209 291h62v131h-62Z','#B99472')+p('M82 256 C31 195 112 111 161 129 C151 35 315 41 318 123 C412 73 471 204 399 248 C443 344 292 379 246 323 C160 383 69 340 82 256Z',G),
'roots': p('M240 78v210 M240 181l-72-44 M242 221l87-72 M240 288l-111 117 M237 318l57 85 M183 348l-96-8 M282 359l103 27',stroke='#9D795B')+p('M72 266h339'),
'ecosystem': c(240,240,163,W)+p('M137 306v-80 M101 236l36-79 38 79Z',G)+p('M302 320q45-61 87 0q-45 61-87 0Z',B)+c(320,124,29,Y)+p('M182 102q48-32 86 0 M180 97l2 20 22-5 M256 381q-46 21-80-1'),
'pencil': p('M92 333L317 76L385 135L159 394L73 419Z',Y)+p('M92 333l67 61 M298 97l67 61 M73 419l12-40 21 19Z',INK),
'blackboard': r(57,96,367,263,G)+p('M117 359l-30 67 M363 359l29 67 M112 155h215 M112 214h159 M111 274h251',stroke=W),
'graduation-cap': p('M41 190L240 93L436 190L240 286Z',B)+p('M128 244v102q112 58 225 0V244',B)+p('M435 191v143')+c(435,351,13,Y),
'backpack': r(119,137,246,273,B,58)+p('M175 138V99q65-64 129 0v39')+r(146,265,191,111,Y)+p('M153 192h175 M94 219v145 M390 219v145'),
'idea': c(240,177,102,Y)+p('M187 264l11 72h85l11-72 M207 363h66 M218 386h43')+p('M111 91l-32-29 M86 184H44 M369 90l30-29 M395 184h42'),
'question': p('M153 156C135 41 381 56 336 187C317 235 237 225 235 291',stroke=B)+c(235,365,21,R),
'trophy': p('M149 92h183v148q-91 105-183 0Z',Y)+p('M149 117H68q-20 137 109 112 M332 117h83q15 137-105 112 M240 292v84 M161 403h157 M180 376h120'),
'calendar': r(76,119,333,278,W)+p('M76 191h333 M149 84v70 M336 84v70')+''.join(r(x,y,28,24,col,3) for x,y,col in [(128,226,Y),(226,226,G),(324,226,B),(128,312,R),(226,312,G),(324,312,Y)]),
'heart': p('M240 412C203 371 64 278 71 168C78 43 206 72 240 149C281 63 410 55 417 177C422 281 279 374 240 412Z',R)+p('M106 248h72l26-54 43 108 30-55h97',stroke=W),
'lungs': p('M239 77v113 M239 152l-51 65 M241 155l52 60')+p('M196 128C146 80 72 201 76 336C77 401 185 427 211 370V213Z',R)+p('M285 130C337 80 410 202 405 336C404 401 298 427 272 370V212Z',R)+p('M188 217l-52 94 M294 217l53 94 M164 262l-43-7 M318 262l39-8'),
'brain': p('M241 105C153 29 77 104 95 162C29 180 43 291 99 309C72 387 171 425 240 375C310 430 411 383 385 309C446 279 447 176 385 161C405 85 310 35 241 105Z',R)+p('M240 105v270 M130 151q70-27 56 38 M100 243q68-28 79 45 M298 120q-53 40 1 67 M385 265q-72-57-70 25'),
'stethoscope': p('M121 78v118q0 123 121 124q115-1 115-124V78',B)+p('M241 320v41q-3 75 91 61q59-6 58-78')+c(392,312,38,Y)+p('M103 77h38 M339 77h39'),
'medical-kit': r(74,160,332,232,W)+p('M171 160v-54h139v54')+p('M215 221h51v51h51v51h-51v51h-51v-51h-51v-51h51Z',R),
'bandage': p('M93 298L297 91Q333 65 373 106Q410 143 382 179L175 385Q141 411 101 375Q63 338 93 298Z',Y)+r(184,184,117,117,W)+''.join(c(x,y,4,INK) for x,y in [(212,212),(244,212),(274,212),(212,246),(244,246),(274,246),(212,277),(244,277),(274,277)]),
'tooth': p('M240 113C153 42 66 111 103 239C124 311 111 422 161 420C210 420 190 281 240 295C293 281 270 420 319 420C365 420 354 311 379 239C416 112 329 42 240 113Z',W)+p('M141 151q5-33 38-23',stroke=B),
'syringe': p('M86 340L290 112L373 187L170 410Z',W)+p('M283 117l76-85 91 82-76 84 M309 73l89 80 M133 372l-65 72')+p('M137 284l64 57 M181 235l36 32 M217 195l36 32')+p('M106 330l81 73',B),
'coins': ''.join(c(x,y,74,Y)+p(f'M{x} {y-38}v76 M{x-24} {y-24}h35q29 12 0 27h-25q-28 16 0 30h37') for x,y in [(167,281),(307,191)]),
'growth-chart': p('M82 72v333h333')+r(125,276,55,105,G)+r(224,211,55,170,B)+r(325,131,55,250,R)+p('M115 231l91-79 68 18 93-94 M339 79l28-3-2 28'),
'wallet': r(71,127,346,237,G)+r(291,200,143,84,Y)+c(334,241,11,INK)+p('M90 127l255-47 25 47',W),
'bank': p('M51 147L240 54L431 147Z',B)+p('M60 393h365 M91 369h302')+''.join(r(x,175,49,176,W,2) for x in [107,218,328]),
'piggy-bank': p('M111 187C167 104 335 108 365 229L425 229v75h-57l-16 85h-49l-12-54H179l-12 54h-49l-9-89Q62 260 88 211Z',R)+p('M177 146h115 M127 177l-9-70 85 34')+c(341,205,12,INK)+p('M88 218Q36 168 46 238'),
'invoice': p('M124 67h234v348l-29-19-30 19-31-19-31 19-29-19-30 19-29-19-25 19Z',W)+p('M165 133h150 M165 187h95 M165 267h150 M165 321h150')+c(309,197,24,Y),
'calculator': r(129,59,222,365,B)+r(153,85,174,77,W)+''.join(r(x,y,35,37,Y if x==280 else W,4) for x in [155,217,280] for y in [195,267,339]),
'handshake': p('M40 184l104-50 90 28 94-21 112 61-47 125-78 36-153-23-87-40Z',Y)+p('M144 134l-42 154 M328 141l45 182 M234 162l-66 66q16 38 46 20l53-30 75 91 M182 277l80 67 M215 261l91 73'),
'scales': p('M240 78v330 M100 142h280 M240 94l-18 22 M100 145L43 284h114Z',B)+p('M380 145l-57 139h114Z',Y)+p('M132 411h216 M43 284q57 47 114 0 M323 284q57 47 114 0'),
'gavel': p('M126 131l149-64 42 95-148 65Z','#B99472')+p('M207 198l116 196 49-29-114-195Z','#B99472')+r(84,375,147,45,Y),
'contract': p('M116 64h188l67 66v286H116Z',W)+p('M304 64v66h67 M155 178h173 M155 230h173 M155 282h110')+p('M231 368q36-86 33-19q29-38 44 0l35-21',stroke=B),
'court': p('M54 148L240 57L426 148Z',W)+''.join(r(x,178,48,164,B,2) for x in [92,217,342])+p('M58 373h365 M40 413h401')+c(240,119,18,Y),
'fingerprint': p('M94 275C44 83 423 37 401 277 M131 301C91 139 355 115 360 273 M170 325C118 189 310 151 316 263 M210 350C159 240 270 198 276 266Q294 376 362 379 M237 267q-3 125 69 160',stroke=B),
'law-book': r(100,80,272,331,B)+p('M117 83v312 M144 404h227 M237 150v157 M182 187h111 M182 187l-28 74h55Z',Y)+p('M293 187l-28 74h56Z',Y)+p('M196 307h84'),
'car': p('M67 249l60-104h228l57 104v103H67Z',B)+p('M159 166h77v74H117Z',W)+p('M259 166h77l41 74H259Z',W)+c(137,347,42,INK)+c(348,347,42,INK)+c(137,347,18,W)+c(348,347,18,W)+r(80,277,48,24,Y)+r(354,277,43,24,Y),
'bicycle': c(112,327,77,B)+c(368,327,77,B)+p('M112 327l87-138 71 138H112 M199 189h92l77 138 M270 327l21-138-18-58 M251 129h66 M177 172h53')+c(270,327,13,Y),
'traffic-light': r(164,59,156,333,INK,40)+c(240,125,42,R)+c(240,225,42,Y)+c(240,325,42,G)+p('M240 393v58'),
'charging-station': r(91,92,225,321,B)+r(120,124,167,123,W)+p('M237 278h-50l23 56h-48l30 61')+p('M316 186q68 0 70 78v64q-1 58 37 56v-159 M404 226h37v-61h-37Z',G),
'wheel': c(240,240,175,INK)+c(240,240,127,B)+c(240,240,26,W)+''.join(p(d) for d in ['M240 114v100','M350 176l-88 51','M350 304l-89-51','M240 366V266','M130 304l87-51','M130 176l88 51']),
'engine': p('M103 161h69v-55h133v56h70v43h52v117h-52v43H103v-72H64v-73h39Z',B)+p('M189 76h94 M210 165v103h102 M164 314h124'),
'road': p('M192 66h95l96 355H95Z',INK)+p('M240 90v55 M240 195v58 M240 305v74',stroke=Y),
'steering-wheel': c(240,240,168,B)+c(240,240,58,Y)+p('M82 196l105 21 M398 196l-105 21 M240 297v105'),
'scroll': p('M115 82h244v312H115Z',W)+p('M115 82q-57-29-59 22q-1 43 58 19 M360 395q59 30 59-22q0-44-59-21 M156 146h161 M156 206h161 M156 266h123'),
'castle': p('M69 119h42v43h35v-43h42v85h105v-85h42v43h35v-43h42v275H69Z',B)+p('M195 394V291q45-62 89 0v103Z',W)+r(95,222,45,64,Y)+r(337,222,45,64,Y),
'hourglass': p('M128 68h224 M128 414h224 M147 68q-4 104 73 173q-77 66-73 173 M333 68q4 104-73 173q77 66 73 173')+p('M177 136h126l-63 80Z',Y)+p('M176 380l64-75 65 75Z',Y),
'globe': c(240,234,151,B)+p('M96 189l88-69 27 61-43 67 38 46-42 57-49-38 M300 107l-29 69 63 18-17 65 57 52 26-63',G)+p('M91 394q239 42 318-230 M241 411v39 M165 452h152'),
'ancient-vase': p('M188 77h109 M199 77v93C59 230 157 431 240 418C343 431 423 231 284 170V77Z',Y)+p('M139 259h208 M148 326h188 M181 236l30 14 29-14 31 14 29-14'),
'ship': p('M62 297h359l-51 100H115Z',B)+p('M239 78v219 M217 107L217 277H90Z',W)+p('M259 95L259 277H387Z',Y)+p('M52 422q35-23 71 0t71 0t71 0t71 0t71 0',stroke=B),
'quill': p('M99 387C120 126 274 40 405 69C421 199 322 335 99 387Z',W)+p('M85 411L353 117 M158 335l-13-104 M205 288l117 1 M253 240l-10-79'),
'museum': p('M51 158L240 70L429 158Z',Y)+r(78,169,329,220,W)+''.join(r(x,188,40,171,B,1) for x in [112,220,328])+p('M56 419h370'),
}

GROUPS = [
('life-agriculture','生活与农业',[
('watermelon','完整西瓜','西瓜 水果 瓜果 watermelon melon'),('watermelon-slice','西瓜切片','瓜瓤 瓜皮 切开的西瓜 watermelon slice rind pulp'),('melon-seedling','瓜苗','幼苗 发芽 苗圃 seedling sprout'),('leaf','叶片','植物 叶子 leaf plant'),('apple','苹果','水果 apple fruit'),('wheat','麦穗','小麦 粮食 农作物 wheat grain'),('soil','土壤','耕作 泥土 soil farming'),('watering-can','洒水壶','浇水 灌溉 watering irrigation'),('sun','太阳','阳光 日照 sun sunlight'),('book','打开的书','书籍 阅读 教材 book textbook reading')]),
('computing-ai','计算机与 AI',[
('laptop','笔记本电脑','计算机 编程 laptop computer coding'),('chip','芯片','处理器 半导体 chip processor'),('network','网络节点','神经网络 连接 network neural connections'),('database','数据库','数据存储 database storage'),('robot','机器人','智能体 agent robot artificial intelligence'),('magnifier','放大镜','搜索 检查 检索 search inspect retrieval'),('decision-tree','决策树符号','分类 决策 decision tree classification'),('cloud','云端','云计算 cloud computing'),('shield','安全盾牌','网络安全 保护 security protection'),('data-table','数据表格','样本 数据集 数据表 dataset samples table')]),
('mathematics','数学',[
('compass','圆规','作图 圆 compass circle'),('ruler','尺子','长度 测量 ruler measurement'),('abacus','算盘','计数 算术 abacus counting'),('dice','骰子','概率 随机 dice probability random'),('coordinate-plane','坐标与曲线符号','函数 曲线 坐标 function coordinate curve'),('geometry-shapes','几何图形','三角形 正方形 圆形 geometry triangle circle'),('balance','平衡符号','等式 平衡 balance equality'),('fraction-pie','分数饼图符号','分数 部分 整体 fraction part whole')]),
('physics-engineering','物理与工程',[
('light-bulb','灯泡','电灯 发光 bulb light'),('battery','电池','电源 电压 battery power voltage'),('magnet','磁铁','磁力 磁场 magnet magnetic field'),('spring','弹簧','弹性 振动 spring elasticity vibration'),('pendulum','摆锤','单摆 周期 pendulum period'),('wave','波形','声波 波动 wave sound oscillation'),('prism','棱镜','折射 光谱 prism refraction spectrum'),('gear','齿轮','机械 传动 gear machine'),('circuit','电路符号','电阻 电流 串联 并联 circuit resistance current'),('thermometer','温度计','温度 热量 thermometer temperature')]),
('chemistry','化学',[
('flask','烧瓶','实验 反应 flask experiment reaction'),('test-tubes','试管','溶液 实验 test tube solution'),('molecule','分子符号','分子 化学键 molecule bond'),('atom','原子符号','原子 电子 atom electron'),('drop','液滴','水滴 液体 drop liquid water'),('crystal','晶体','结晶 晶格 crystal lattice'),('pipette','滴管','滴定 移液 pipette titration'),('beaker','烧杯','溶解 容器 beaker dissolution')]),
('biology','生物',[
('dna','DNA 符号','遗传 脱氧核糖核酸 dna genetics'),('cell','细胞符号','细胞膜 细胞核 cell nucleus membrane'),('microscope','显微镜','观察 微生物 microscope microbe'),('butterfly','蝴蝶','昆虫 变态 butterfly insect'),('fish','鱼','水生 生物 fish aquatic'),('tree','树木','光合作用 植物 tree photosynthesis'),('roots','根系','吸收 根 植物 root absorption'),('ecosystem','生态系统符号','生态 食物链 ecosystem ecology')]),
('education','教育',[
('pencil','铅笔','书写 学习 pencil writing'),('blackboard','黑板','教学 课堂 blackboard classroom'),('graduation-cap','学士帽','毕业 大学 graduation university'),('backpack','书包','学生 学校 backpack student'),('idea','灵感灯泡','思考 创意 idea thinking creativity'),('question','问号','提问 疑问 question inquiry'),('trophy','奖杯','目标 成就 trophy achievement'),('calendar','日历','计划 时间管理 calendar schedule')]),
('medicine','医疗',[
('heart','心脏符号','心脏 心跳 血液 heart heartbeat blood'),('lungs','肺部符号','呼吸 肺泡 气体交换 lungs respiration oxygen alveoli'),('brain','大脑符号','神经 大脑 brain nerve'),('stethoscope','听诊器','诊断 听诊 stethoscope diagnosis'),('medical-kit','医药箱','急救 医疗 first aid medicine'),('bandage','创可贴','伤口 护理 bandage wound'),('tooth','牙齿','口腔 牙科 tooth dental'),('syringe','注射器','疫苗 注射 syringe vaccine injection')]),
('finance','金融',[
('coins','硬币','货币 金钱 本金 coin money principal'),('growth-chart','增长图符号','复利 利率 收益 增长 compound interest growth returns'),('wallet','钱包','支付 消费 wallet payment spending'),('bank','银行','存款 银行 bank deposit'),('piggy-bank','储蓄罐','储蓄 积蓄 saving piggy bank'),('invoice','账单','发票 费用 invoice bill cost'),('calculator','计算器','计算 预算 calculator budget'),('handshake','握手','交易 合作 handshake trade cooperation')]),
('law','法律',[
('scales','司法天平','公平 正义 司法 justice fairness scales'),('gavel','法槌','审判 法庭 gavel trial'),('contract','合同','协议 签字 contract agreement signature'),('court','法院','法院 法律 court law'),('fingerprint','指纹','证据 身份 fingerprint evidence identity'),('law-book','法典','法律 条文 code statute law book')]),
('automotive-transport','汽车交通',[
('car','汽车','车辆 汽车 car vehicle'),('bicycle','自行车','骑行 bicycle cycling'),('traffic-light','红绿灯','交通 信号 traffic light signal'),('charging-station','充电桩','电动车 充电 electric vehicle charging'),('wheel','车轮','轮胎 车轮 wheel tire'),('engine','发动机','动力 引擎 engine motor'),('road','公路','道路 路线 road route'),('steering-wheel','方向盘','驾驶 转向 steering driving')]),
('history','历史',[
('scroll','卷轴','史料 记录 scroll chronicle record'),('castle','城堡','古城 建筑 castle ancient city'),('hourglass','沙漏','时间 年代 hourglass time chronology'),('globe','地球仪','地理 世界 globe geography world'),('ancient-vase','古代陶瓶','陶器 文物 pottery relic vase'),('ship','帆船','航海 贸易 ship navigation'),('quill','羽毛笔','书信 文献 quill letter manuscript'),('museum','博物馆','文化 文物 museum heritage')]),
]

ENTITY_ALIASES = {
    'watermelon':['西瓜','watermelon'], 'watermelon-slice':['西瓜切片','切开的西瓜','watermelon slice'],
    'melon-seedling':['瓜苗','幼苗','seedling','sprout'], 'laptop':['笔记本电脑','计算机','电脑','computer','laptop'],
    'lungs':['肺部','肺脏','lungs','lung'], 'heart':['心脏','heart'],
    'brain':['大脑','brain'], 'cell':['细胞','cell'],
    'data-table':['数据表','表格','table','data table'], 'network':['神经网络','网络节点','network'],
    'circuit':['电路','circuit'], 'light-bulb':['灯泡','电灯','bulb'],
    'growth-chart':['增长图','增长曲线','growth chart'],
    'coins':['硬币','coins','coin'], 'steering-wheel':['方向盘','steering wheel'],
    'magnifier':['放大镜','magnifier','magnifying glass'],
}


def pencil_art(key, drawing):
    """Original vector pencil passes and hatching, clipped by sampled silhouettes.

    The PNG is only a geometric mask for authoring new vector strokes. Delivered
    assets remain editable SVG, with no filters, image embeddings or external refs.
    """
    import resvg_py
    from PIL import Image
    base=ET.fromstring('<g>'+drawing+'</g>')
    for i,node in enumerate(base):
        node.set('stroke-width',str(3.6+(i%3)*.4))
    thin=copy.deepcopy(base)
    for node in thin:
        node.set('fill','none');node.set('stroke-width','1.25')
    fill_drawing=ET.tostring(base,encoding='unicode')
    mask_svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="480"><g stroke="{INK}" stroke-width="4">{fill_drawing}</g></svg>'
    mask=Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=mask_svg))).convert('RGBA')
    offset=int(hashlib.sha256(key.encode()).hexdigest()[:2],16)%24
    strokes=[]
    for intercept in range(-360+offset,900,27):
        run=[]
        for x in range(28,451,2):
            y=intercept-x*.65
            if not 25<y<454:
                inside=False
            else:
                red,green,blue,alpha=mask.getpixel((x,round(y)))
                inside=alpha>240 and red+green+blue>260
            if inside:run.append((x,y))
            if (not inside or x==450) and run:
                if len(run)>4:
                    a,b=run[0],run[-1]
                    strokes.append(f'<path d="M{a[0]} {a[1]:.1f} L{b[0]} {b[1]:.1f}"/>')
                run=[]
    return (f'<g stroke="{INK}" stroke-linecap="round" stroke-linejoin="round">{fill_drawing}</g>'+
            f'<g stroke="{INK}" stroke-opacity=".20" stroke-width="1.1" fill="none">'+''.join(strokes)+'</g>'+
            f'<g stroke="{INK}" stroke-opacity=".42" transform="translate(.7 -.5)" fill="none">'+ET.tostring(thin,encoding='unicode')+'</g>')


def build():
    count = 0
    ROOT.mkdir(parents=True, exist_ok=True)
    root_lines = ['# 教学插画与符号库', '', '100 个原创线条符号；透明背景。另见各领域 handdrawn 子目录的有出处手绘插画。', '',
                  '每个子目录 README 的 TOML 条目是素材索引的唯一描述来源。添加素材后运行 `python scripts/index_visual_assets.py --check`。', '',
                  '这些图用于教学配图；符号不是按比例的数学、解剖或实验结果。原创符号采用 MIT；外部手绘插画的作者与许可由其 README 逐项列出。', '', '| 子目录 | 内容 | 原创符号数量 |', '| --- | --- | --- |']
    for domain, title, items in GROUPS:
        folder = ROOT / domain; folder.mkdir(exist_ok=True)
        root_lines.append(f'| [{domain}]({domain}/README.md) | {title} | {len(items)} |')
        lines = [f'# {title}', '', '下表中的素材均为原创透明 SVG 符号，用于实际讲解对象旁的辅助配图。', '',
                 '| 素材 | 画面描述 |', '| --- | --- |']
        metadata = []
        for key, name, aliases in items:
            description = f'{name}：简化线条符号、双轮廓与排线，独立透明画布。不是手绘实例插画。'
            limitation = '概念性配图；不代表尺寸、数量、正确分类或实验数据。'
            if key in {'coordinate-plane','fraction-pie','decision-tree','network','molecule','atom','heart','lungs','brain','cell','dna','ecosystem','circuit','growth-chart'}:
                limitation += '符号不是教材公式、解剖结构或关系证明，需配合独立教学演示。'
            svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="480" height="480" viewBox="0 0 480 480">'
                   f'<title>{html.escape(name)}</title><desc>{html.escape(description)}</desc>'
                   + pencil_art(key,D[key])+'</svg>')
            (folder/f'{key}.svg').write_text(svg, encoding='utf-8')
            lines.append(f'| [{name}]({key}.svg) | {description} |')
            record = {'id': f'{domain}.{key}', 'file': f'{key}.svg', 'title': name, 'description': description,
                      'tags': aliases.split(' '), 'entity_aliases':ENTITY_ALIASES.get(key,
                          [name,name.removeprefix('打开的').removeprefix('完整').removesuffix('符号'),key.replace('-',' ')]),
                      'domain': domain, 'usage': f'{title}相关讲解中，对应真实对象或明确概念的辅助配图。',
                      'limitations': limitation, 'source': 'Book2Course 原创；scripts/build_original_visuals.py', 'license': 'MIT'}
            metadata.append('[[assets]]\n'+'\n'.join(f'{k} = {json.dumps(v, ensure_ascii=False)}' for k,v in record.items()))
            count += 1
        lines += ['', '## 机器可读描述', '', '```toml', '\n\n'.join(metadata), '```', '']
        children=[p for p in folder.iterdir() if p.is_dir()]
        if children:
            lines += ['## 下级目录','',*[f'- [{p.name}]({p.name}/README.md)' for p in sorted(children)],'']
        (folder/'README.md').write_text('\n'.join(lines), encoding='utf-8')
    (ROOT/'README.md').write_text('\n'.join(root_lines)+'\n', encoding='utf-8')
    assert count == 100 and len(D) == 100, (count, len(D))
    print(f'Created {count} original SVG illustrations.')

if __name__ == '__main__':
    build()
