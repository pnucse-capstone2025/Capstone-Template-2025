# SSD Write Amplification Analysis - Capstone Project 2025
## SSD 쓰기 증폭 분석 - 졸업과제 2025

This repository contains a modified version of SimpleSSD v2.0 for analyzing Write Amplification Factor (WAF) with hotness-based labeling in Flash Translation Layer (FTL) algorithms.

이 저장소는 플래시 변환 계층(FTL) 알고리즘에서 핫니스 기반 라벨링을 통한 쓰기 증폭 계수(WAF) 분석을 위해 수정된 SimpleSSD v2.0을 포함합니다.

---

## Project Purpose | 프로젝트 목적


This project is developed as a capstone research project to study the impact of hotness labeling on Write Amplification Factor in SSD storage systems. The primary focus is on understanding how data hotness classification affects garbage collection behavior and overall write amplification.


본 프로젝트는 SSD 저장 시스템에서 핫니스 라벨링이 쓰기 증폭 계수에 미치는 영향을 연구하기 위한 졸업과제 연구 프로젝트로 개발되었습니다. 데이터 핫니스 분류가 가비지 컬렉션 동작과 전체 쓰기 증폭에 어떤 영향을 미치는지 이해하는 것이 주요 목적입니다.

---

## License | 라이센스

This project is based on SimpleSSD v2.0, which is licensed under GNU General Public License v3.0. All modifications and additions maintain the same GPL v3.0 license.

이 프로젝트는 GNU General Public License v3.0으로 라이센스된 SimpleSSD v2.0을 기반으로 합니다. 모든 수정사항과 추가사항은 동일한 GPL v3.0 라이센스를 유지합니다.

**Original Project:** [SimpleSSD v2.0](http://simplessd.org) by CAMELab  
**License:** GNU General Public License v3.0 (see LICENSE file)

---

## Key Modifications | 주요 수정사항

**English:**
1. **Real-time WAF Monitoring**: Added live Write Amplification Factor tracking during simulation
2. **Enhanced Statistics**: Improved WAF calculation with separate tracking for user writes and GC writes


**Korean:**
1. **실시간 WAF 모니터링**: 시뮬레이션 중 실시간 쓰기 증폭 계수 추적 기능 추가
2. **향상된 통계**: 사용자 쓰기와 GC 쓰기를 분리 추적하는 개선된 WAF 계산

---

## Code Changes | 코드 변경사항

### Modified Files | 수정된 파일:

- **`simplessd/ftl/page_mapping.cc`**: Added real-time WAF monitoring and enhanced statistics tracking
- **Configuration files**: Modified for research-specific parameters and reduced SSD size for testing
- **Trace files**: Added hotness-labeled traces for analysis

### Key Features | 주요 기능:

- Live WAF display every 1000 write operations
- Detailed GC event monitoring with WAF updates
- Separate tracking of host writes, device writes, user writes, and GC writes
- Real-time terminal output for demonstration purposes

---

## Usage Notes | 사용 주의사항

**English:**
- **Configuration Compatibility**: The configuration files in this repository have been significantly modified from the original SimpleSSD. If you need standard SimpleSSD functionality, please refer to the original project.
- **Research Focus**: This version is specifically optimized for WAF analysis with hotness labeling. For general SSD simulation, use the original SimpleSSD.
- **FTL Reference**: The core FTL (Flash Translation Layer) algorithms remain largely unchanged and can be used as reference for standard page mapping implementations.

**Korean:**
- **설정 호환성**: 이 저장소의 설정 파일들은 원본 SimpleSSD에서 크게 수정되었습니다. 표준 SimpleSSD 기능이 필요한 경우 원본 프로젝트를 참조하세요.
- **연구 목적**: 이 버전은 핫니스 라벨링을 통한 WAF 분석에 특화되어 최적화되었습니다. 일반적인 SSD 시뮬레이션을 위해서는 원본 SimpleSSD를 사용하세요.
- **FTL 참조**: 핵심 FTL(플래시 변환 계층) 알고리즘은 대부분 변경되지 않았으며 표준 페이지 매핑 구현의 참조로 사용할 수 있습니다.

---



## Academic Use | 학술적 사용

This project is developed for educational and research purposes. If you use this code for academic research, please cite both the original SimpleSSD project and acknowledge this modification for capstone research.

이 프로젝트는 교육 및 연구 목적으로 개발되었습니다. 학술 연구에 이 코드를 사용하는 경우, 원본 SimpleSSD 프로젝트를 인용하고 졸업과제 연구를 위한 이 수정사항을 인정해 주시기 바랍니다.

---

## Contact | 연락처

For questions related to this capstone project modifications, please refer to the commit history and code comments.

졸업과제 프로젝트 수정사항에 관한 질문은 커밋 히스토리와 코드 주석을 참조하시기 바랍니다.

**Original SimpleSSD:** [SimpleSSD Website](http://simplessd.org) | [CAMELab](http://camelab.org)