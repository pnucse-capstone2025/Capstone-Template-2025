# 출처 및 라이선스
## SimpleSSD version 2.0
Open-Source Licensed Educational SSD Simulator for High-Performance Storage and Full-System Evaluations

This project is managed by [CAMELab](http://camelab.org).
For more information, please visit [SimpleSSD homepage](http://simplessd.org).
SimpleSSD is released under the GPLv3 license. See `LICENSE` file for details.

- 클론(원본 출처): `git clone git@github.com:simplessd/simplessd-standalone`
- 문서 기준 버전: SimpleSSD 문서 v2.0.12
- 원 라이선스: GNU GPLv3
- 라이선스 적용: 본 프로젝트는 SimpleSSD 문서(v2.0.12)에 명시된 대로 **GPLv3 라이선스**를 그대로 차용하며, 원저작권/라이선스 고지를 유지합니다.

# 목적 (Purpose)
It uses the method of first-touching the block by naming the Hotness label included in the write request as a variable called temperature. The tagged block will only accept data at the same temperature until full, and will be closed when full. After that, when a block is erased from the Garbage Collection (GC), the tag will be removed and returned to the free block, and a page_mapping_hotness file will be added for reuse in any temperature pool.

쓰기 요청에 포함된 Hotness 레이블을 temperature라는 변수로 명명하여 블록을 첫 태깅(first-touch) 하는 방식을 사용합니다. 태깅된 블록은 가득 찰 때까지 동일 온도의 데이터만 수용하며, 가득 차면 닫힘(closed) 상태가 됩니다. 이후 가비지 컬렉션(GC)에서 블록이 소거(erase) 되면 태그가 제거되어 free 블록으로 환원되고, 어떤 온도 풀에서든 재사용될 수 있도록 하기 위해서 page_mapping_hotness 파일을 추가하게 되었습니다.

# 변경 사실
This repository contains the following changes to the source.
- Trace Replayer: Parsing and Injecting Labels
Safely parses the Hotness field in one line of trace.
- None Driver (sil/none): Forward BIO→HIL
Copy the BIO to req.temperature= bio.temperature without loss when converting it to HIL::Request.
- ICL Correction: Preserving labels with cache sidecar and re-injecting Flush
To prevent the label from being lost during ICL's write buffering, merging, and eviction process, introduce cache-line sidecar metadata and re-inject it into FTL requests during flushing.
- FTL modification for Hotness page mapping: label normalization, pool selection, consistent GC/WAF calculation
Receive and normalize req.temperature at FTL inlet (0-3) and select free block in label pool for physical separation recording. Label statistics and WAF are also aggregated and exposed in this module.

본 저장소에는 원본 대비 다음 변경이 포함됩니다.
- Trace Replayer: 레이블 파싱·주입
트레이스 한 줄에서 Hotness 필드를 안전하게 정수 파싱합니다.
- None 드라이버(sil/none): BIO→HIL 전달
BIO를 HIL::Request로 변환할 때 req.temperature = bio.temperature로 손실 없이 복사합니다.
- ICL 수정: 캐시 사이드카로 레이블 보존·Flush 재주입
ICL의 쓰기 버퍼링·병합·에빅션 과정에서 레이블이 소실되지 않도록, 캐시라인 단위 사이드카 메타데이터를 도입하고 flush 시 FTL 요청에 재주입합니다.
- Hotness page mapping을 위한 FTL 수정 : 레이블 정규화·풀 선택·일관 GC·WAF 산출
FTL 입구에서 req.temperature를 수신·정규화하고(0~3), 레이블별 풀(Pool)에서 free 블록을 선택해 물리적 분리 기록을 수행합니다. 레이블별 통계와 WAF도 본 모듈에서 집계·노출합니다.
