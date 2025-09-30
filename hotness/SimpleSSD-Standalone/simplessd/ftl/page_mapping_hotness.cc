#include "ftl/page_mapping_hotness.hh"

#include <algorithm>
#include <limits>
#include <random>
#include <cstring>
#include <array>
#include "util/algorithm.hh"
#include "util/bitset.hh"
#include <inttypes.h>

namespace SimpleSSD { namespace FTL {

PageMappingHotness::PageMappingHotness(ConfigReader& c, Parameter& p, PAL::PAL* l, DRAM::AbstractDRAM* d)
  : AbstractFTL(p,l,d), pPAL(l), conf(c),
    lastFreeBlockIOMap(param.ioUnitInPage),
    bReclaimMore(false),
    reservePerPool(0)
{
 reservePerPool = std::max<uint32_t>(1u, param.totalPhysicalBlocks / (4u * 64u));

  // free block을 미지정 shard(4분할)로 균등 분배 (blockIdx % 4)
  for (uint32_t i = 0; i < param.totalPhysicalBlocks; i++) {
    uint8_t d = i & 3;
    freeBlocksByT[d].emplace_back(Block(i, param.pagesInBlock, param.ioUnitInPage));
    nFreeByT[d]++;
  }

  // last-free 초기화: 초기에는 어떤 풀에도 태깅하지 않음(미지정).
  for (uint8_t t = 0; t < 4; ++t) {
    lastFreeBlockByT[t].assign(param.pageCountToMaxPerf, param.totalPhysicalBlocks); // INVALID sentinel
    lastFreeIdx[t] = 0;
  }

  status.totalLogicalPages = param.totalLogicalBlocks * param.pagesInBlock;

//  memset(&stat, 0, sizeof(stat));
  bRandomTweak = conf.readBoolean(CONFIG_FTL, FTL_USE_RANDOM_IO_TWEAK);
  bitsetSize   = bRandomTweak ? param.ioUnitInPage : 1;
}

PageMappingHotness::~PageMappingHotness() {}

bool PageMappingHotness::initialize() {
  debugprint(LOG_FTL_PAGE_MAPPING, "Hotness-FTL Initialization finished");
  return true;
}

float PageMappingHotness::freeBlockRatio(uint8_t t) {
  uint64_t headroomPages = 0;

  for (auto& kv : blocks) {
    const uint32_t bid = kv.first;
    auto& blk = kv.second;

    auto it = blockPool.find(bid);
    if (it != blockPool.end() && it->second == t) {
      const uint32_t wp = blk.getNextWritePageIndex();
      if (wp < param.pagesInBlock) {
        headroomPages += (uint64_t)(param.pagesInBlock - wp);
      }
    }
  }

  const uint64_t denom = (uint64_t)param.pagesInBlock; // 최소 1블록 헤드룸을 기준
  if (denom == 0) return 0.0f;

  float r = (float)headroomPages / (float)denom;
  if (r > 1.0f) r = 1.0f; // 과도하게 많은 오픈 블록이 있어도 1로 클램프
  return r;
}


uint32_t PageMappingHotness::borrowFreeBlock(uint8_t t, uint32_t stripeIdx) {
  for (uint8_t d = 0; d < 4; ++d) {
    if (freeBlocksByT[d].empty()) continue;

    auto it = freeBlocksByT[d].begin();
    uint32_t blockIndex = 0;
    for (; it != freeBlocksByT[d].end(); ++it) {
      blockIndex = it->getBlockIndex();
      if (blockIndex % param.pageCountToMaxPerf == stripeIdx) break;
    }
    if (it == freeBlocksByT[d].end()) { it = freeBlocksByT[d].begin(); blockIndex = it->getBlockIndex(); }

    blocks.emplace(blockIndex, std::move(*it));
    freeBlocksByT[d].erase(it);
    nFreeByT[d]--;

    stat.allocPop[d]++;
    blockPool[blockIndex] = t; // 재태깅 중요
    return blockIndex;
  }
  return param.totalPhysicalBlocks; // 실패
}

uint32_t PageMappingHotness::getFreeBlock(uint8_t t, uint32_t stripeIdx) {
  if (stripeIdx >= param.pageCountToMaxPerf) panic("Index out of range");

  // Fully-unassigned: 어떤 도너 shard(0..3)에서든 하나 꺼내 첫-터치 태깅
  auto pick_from = [&](uint8_t d)->int32_t {
    if (freeBlocksByT[d].empty()) return -1;

    // 같은 stripe 우선
    auto it = freeBlocksByT[d].end();
    uint32_t blockIndex = 0;
    for (auto it2 = freeBlocksByT[d].begin(); it2 != freeBlocksByT[d].end(); ++it2) {
      blockIndex = it2->getBlockIndex();
      if ((blockIndex % param.pageCountToMaxPerf) == stripeIdx) { it = it2; break; }
    }
    if (it == freeBlocksByT[d].end()) {
      it = freeBlocksByT[d].begin();
      blockIndex = it->getBlockIndex();
    }

    if (blocks.find(blockIndex) != blocks.end())
      panic("Corrupted: free->alloc double-take");

    // ★ 첫-터치 태깅
    blockPool[blockIndex] = t;
    blocks.emplace(blockIndex, std::move(*it));
    freeBlocksByT[d].erase(it);
    nFreeByT[d]--;

    stat.allocPop[d]++;
    return static_cast<int32_t>(blockIndex);
  };

  // stripe 해시 기준 라운드로빈
  for (uint8_t off = 0; off < 4; ++off) {
    const uint8_t d = static_cast<uint8_t>((stripeIdx + off) & 3);
    int32_t bid = pick_from(d);
    if (bid >= 0) return static_cast<uint32_t>(bid);
  }

  // 최후 수단: 기존 borrow 경로
  auto b = borrowFreeBlock(t, stripeIdx);
  if (b < param.totalPhysicalBlocks) return b;

  panic("No free block left");
  return param.totalPhysicalBlocks; // -Wreturn-type 억제 (panic이 noreturn 아닐 때)
}



uint32_t PageMappingHotness::getLastFreeBlock(uint8_t t, Bitset& iomap) {
  // 1) I/O lane 라운드로빈 (원본과 동일한 조건)
  if (!bRandomTweak || (lastFreeBlockIOMap & iomap).any()) {
    if (++lastFreeIdx[t] == param.pageCountToMaxPerf) lastFreeIdx[t] = 0;
    lastFreeBlockIOMap = iomap;
  } else {
    lastFreeBlockIOMap |= iomap;
  }

  const uint32_t lane = lastFreeIdx[t];
  uint32_t &bid = lastFreeBlockByT[t][lane];

  // 2) 캐시된 블록이 없으면 즉시 확보(풀 t에서)
  auto it = blocks.find(bid);
  if (it == blocks.end()) {
    bid = getFreeBlock(t, lane);            // first-touch 기반: 글로벌 free에서 가져오고 태깅
    blockPool[bid] = t;                     // (안전)
    return bid;
  }

  // 3) 캐시된 free 블록이 꽉 찼으면 교체(+ bReclaimMore)
  if (it->second.getNextWritePageIndex() >= param.pagesInBlock) {
    bid = getFreeBlock(t, lane);            // 글로벌 free에서 확보
    blockPool[bid] = t;                     // (안전)
    bReclaimMore= true;
  }
  return bid;
}



void PageMappingHotness::read(Request& req, uint64_t& tick) {
  uint64_t begin = tick;
  if (req.ioFlag.count() == 0) { warn("FTL got empty request"); return; }
  readInternal(req, tick);
  debugprint(LOG_FTL_PAGE_MAPPING, "READ  | LPN %" PRIu64 " | %" PRIu64 " - %" PRIu64 " (%" PRIu64 ")",
            req.lpn, begin, tick, tick - begin);
  tick += applyLatency(CPU::FTL__PAGE_MAPPING, CPU::READ);
}

void PageMappingHotness::write(Request& req, uint64_t& tick) {
  writeInternal(req, tick, true);
  }

void PageMappingHotness::trim(Request& req, uint64_t& tick) {
  trimInternal(req, tick);
}

void PageMappingHotness::format(LPNRange& , uint64_t& tick) {
  tick += applyLatency(CPU::FTL__PAGE_MAPPING, CPU::FORMAT);
}

void PageMappingHotness::resetStatValues() {
  uint64_t snap[4] = { stat.initFree[0], stat.initFree[1], stat.initFree[2], stat.initFree[3] };
  stat = decltype(stat){};
  for (int t=0; t<4; ++t) stat.initFree[t] = snap[t];
}

Status* PageMappingHotness::getStatus(uint64_t lpnBegin, uint64_t lpnEnd) {
  status.freePhysicalBlocks =
      nFreeByT[0] + nFreeByT[1] + nFreeByT[2] + nFreeByT[3];

  if (lpnBegin == 0 && lpnEnd >= status.totalLogicalPages) {
    status.mappedLogicalPages = table.size();
    return &status;
  }

  uint64_t cnt = 0;
  for (const auto& kv : table) {
    uint64_t lpn = kv.first;              // unordered_map<uint64_t, ...> 가정
    if (lpn >= lpnBegin && lpn < lpnEnd) ++cnt;
  }
  status.mappedLogicalPages = cnt;
  return &status;
}

// ===== 내부 동작 (기본 PageMapping과 거의 동일) =====

void PageMappingHotness::readInternal(Request& req, uint64_t& tick) {
  PAL::Request palRequest(req);
  uint64_t beginAt;
  uint64_t finishedAt = tick;

  auto mappingList = table.find(req.lpn);

  if (mappingList != table.end()) {
    if (bRandomTweak) {
      pDRAM->read(&(*mappingList), 8 * req.ioFlag.count(), tick);
    }
    else {
      pDRAM->read(&(*mappingList), 8, tick);
    }

    for (uint32_t idx = 0; idx < bitsetSize; idx++) {
      if (req.ioFlag.test(idx) || !bRandomTweak) {
        auto &mapping = mappingList->second.at(idx);

        if (mapping.first < param.totalPhysicalBlocks &&
            mapping.second < param.pagesInBlock) {
          palRequest.blockIndex = mapping.first;
          palRequest.pageIndex = mapping.second;

          if (bRandomTweak) {
            palRequest.ioFlag.reset();
            palRequest.ioFlag.set(idx);
          }
          else {
            palRequest.ioFlag.set();
          }

          auto block = blocks.find(palRequest.blockIndex);

          if (block == blocks.end()) {
            panic("Block is not in use");
          }

          beginAt = tick;

          block->second.read(palRequest.pageIndex, idx, beginAt);
          pPAL->read(palRequest, beginAt);

          finishedAt = MAX(finishedAt, beginAt);
        }
      }
    }

    tick = finishedAt;
    tick += applyLatency(CPU::FTL__PAGE_MAPPING, CPU::READ_INTERNAL);
  }
}

void PageMappingHotness::writeInternal(Request& req, uint64_t& tick, bool sendToPAL) {
  PAL::Request pal(req);
  auto mappingList = table.find(req.lpn);
  uint64_t beginAt;
  uint64_t finishedAt = tick;
  bool readBeforeWrite = false;

  // --- 기존 매핑 무효화 / 없으면 삽입 ---
  if (mappingList != table.end()) {
    for (uint32_t i = 0; i < bitsetSize; i++) {
      if (req.ioFlag.test(i) || !bRandomTweak) {
        auto& m = mappingList->second.at(i);
        if (m.first < param.totalPhysicalBlocks && m.second < param.pagesInBlock) {
          auto it = blocks.find(m.first);
          if (it != blocks.end()) it->second.invalidate(m.second, i);
        }
      }
    }
  } else {
    auto ret = table.emplace(
      req.lpn,
      std::vector<std::pair<uint32_t,uint32_t>>(bitsetSize, {param.totalPhysicalBlocks, param.pagesInBlock})
    );
    if (!ret.second) panic("Failed to insert mapping");
    mappingList = ret.first;
  }

  // --- 라벨/서브페이지 수 ---
  const int rawT   = req.temperature;
  const uint8_t reqT = clampTemp(rawT);
  lpnTemp[req.lpn] = reqT;

  // (선택) FTL 입구 원시 라벨 히스토그램
  static uint64_t ftl_entry_raw[5] = {0}; // 0:-1, 1:0, 2:1, 3:2, 4:3
  if      (rawT == -1) ftl_entry_raw[0]++;
  else if (rawT ==  0) ftl_entry_raw[1]++;
  else if (rawT ==  1) ftl_entry_raw[2]++;
  else if (rawT ==  2) ftl_entry_raw[3]++;
  else                 ftl_entry_raw[4]++; // >=3 은 3으로 클램프

  const uint32_t subpages = static_cast<uint32_t>(req.ioFlag.count()); // ★ 4KiB 서브페이지 수

  // --- 기본은 요청 풀 사용, 없으면 인접 풀로 폴백 ---
  uint8_t useT = reqT;

  // --- 실제 사용 풀에서 free 블록 선택 ---
  uint32_t blkId = getLastFreeBlock(useT, req.ioFlag);
  auto blkIt = blocks.find(blkId);
  if (blkIt == blocks.end()) panic("No such block");

  // --- 블록 태그로 실제 사용 풀 확정 ---
  uint8_t actualT = useT;
  {
    auto itp = blockPool.find(blkId);
    if (itp != blockPool.end() && itp->second < 4) actualT = itp->second;
  }

  // --- 통계: "서브페이지 수" 기준으로 딱 1번 누적 ---
  if (reqT    < 4) stat.writesReq[reqT]    += (uint64_t)subpages;
  if (actualT < 4) stat.writesUse[actualT] += (uint64_t)subpages;
  if (reqT < 4 && actualT < 4 && reqT != actualT) {
    stat.fallback[reqT][actualT] += (uint64_t)subpages;
  }

  // --- DRAM 메타 I/O ---
  if (sendToPAL) {
    if (bRandomTweak) {
      pDRAM->read(&(*mappingList),  8 * req.ioFlag.count(), tick);
      pDRAM->write(&(*mappingList), 8 * req.ioFlag.count(), tick);
    } else {
      pDRAM->read(&(*mappingList),  8, tick);
      pDRAM->write(&(*mappingList), 8, tick);
    }
  }

  if (!bRandomTweak && !req.ioFlag.all()) readBeforeWrite = true;

  // --- 실제 쓰기 ---
for (uint32_t i = 0; i < bitsetSize; i++) {
  if (req.ioFlag.test(i) || !bRandomTweak) {
    uint32_t pageIndex = blkIt->second.getNextWritePageIndex(i);
    auto& m = mappingList->second.at(i);
    beginAt = tick;

    blkIt->second.write(pageIndex, req.lpn, i, beginAt);

    if (readBeforeWrite && sendToPAL) {
      pal.blockIndex = m.first;
      pal.pageIndex  = m.second;
      pal.ioFlag     = req.ioFlag; pal.ioFlag.flip();
      pPAL->read(pal, beginAt);
    }

    m.first  = blkIt->first;
    m.second = pageIndex;

    if (sendToPAL) {
      pal.blockIndex = blkIt->first;
      pal.pageIndex  = pageIndex;
      if (bRandomTweak) { pal.ioFlag.reset(); pal.ioFlag.set(i); }
      else               pal.ioFlag.set();
      pPAL->write(pal, beginAt);

      {
  const uint64_t bytesPerSub = param.pageSize / param.ioUnitInPage;
  const uint64_t devBytesRaw = bytesPerSub * static_cast<uint64_t>(pal.ioFlag.count());
  const uint64_t devBytes    = devBytesRaw / 2; // PAL이 1/2 페이지 단위로 program.bytes를 집계
  stat.nandProgramBytes += devBytes;
}

    }

    finishedAt = MAX(finishedAt, beginAt);
  }
}


  if (sendToPAL) {
    tick  = finishedAt;
    tick += applyLatency(CPU::FTL__PAGE_MAPPING, CPU::WRITE_INTERNAL);
  }

  // --- GC 트리거(실사용 풀 기준) ---
  auto clamp01 = [](float v, float def){ return (v>0.f && v<1.f) ? v : def; };
  float low = clamp01(conf.readFloat(CONFIG_FTL, FTL_GC_THRESHOLD_RATIO), 0.10f);

  if (freeBlockRatio(actualT) < low) {
    if (!sendToPAL) panic("ftl: GC triggered during init");

    uint64_t beginAt2 = tick;
    std::vector<uint32_t> victims;

    selectVictimBlock(actualT, victims, beginAt2);
    debugprint(LOG_FTL_PAGE_MAPPING, "GC | pool=%u | victims=%zu",
               (unsigned)actualT, victims.size());
    doGarbageCollection(actualT, victims, beginAt2);

    bReclaimMore = false;
  }

  debugprint(LOG_FTL_PAGE_MAPPING,
    "ALLOC_USE | lpn=%" PRIu64 " | reqT=%u -> useT=%u | blk=%u | pool=%u | free_left=%zu",
    req.lpn, (unsigned)reqT, (unsigned)useT, blkId, (unsigned)actualT,
    freeBlocksByT[useT].size());
}



void PageMappingHotness::trimInternal(Request& req, uint64_t& tick) {
  auto it = table.find(req.lpn);
  if (it != table.end()) {
    if (bRandomTweak) pDRAM->read(&(*it), 8 * req.ioFlag.count(), tick);
    else              pDRAM->read(&(*it), 8, tick);

    for (uint32_t i = 0; i < bitsetSize; i++) {
      auto& m = it->second.at(i);
      auto b  = blocks.find(m.first);
      if (b == blocks.end()) panic("Block not in use");
      b->second.invalidate(m.second, i);
    }
    table.erase(it);
    tick += applyLatency(CPU::FTL__PAGE_MAPPING, CPU::TRIM_INTERNAL);
  }
}

void PageMappingHotness::eraseInternal(PAL::Request& req, uint64_t& tick) {
  // 1) victim block 찾기
  auto it = blocks.find(req.blockIndex);
  if (it == blocks.end()) panic("No such block");

  // 2) 유효 페이지 확인
  if (it->second.getValidPageCount() != 0) panic("Valid pages remain in victim");

  // 3) 실제 erase
  it->second.erase();               // 내부 상태 리셋
  pPAL->erase(req, tick);           // PAL에 erase 발행

  // 4) 완전 미지정 회수: 라벨 해제 후, donor shard를 stripe 기반으로 선택
  //    (균형 유지를 위해 4개 shard로 라운드-로빈 분산)
  uint32_t stripe = req.blockIndex % param.pageCountToMaxPerf;
  uint8_t donor = (uint8_t)(stripe & 3);

  // 라벨 해제
  auto itp = blockPool.find(req.blockIndex);
  if (itp != blockPool.end()) blockPool.erase(itp);

  // free 리스트로 회수
  freeBlocksByT[donor].push_back(std::move(it->second));
  nFreeByT[donor]++;

  // in-use 컨테이너에서 제거
  blocks.erase(it);

  tick += applyLatency(CPU::FTL__PAGE_MAPPING, CPU::ERASE_INTERNAL);
  debugprint(LOG_FTL_PAGE_MAPPING,
             "ERASE | to_unassigned donor=%u block=%u | free(size)=%zu",
             (unsigned)donor, (unsigned)req.blockIndex, freeBlocksByT[donor].size());
}

void PageMappingHotness::calculateTotalPages(uint64_t& valid, uint64_t& invalid) {
  valid = invalid = 0;
  for (auto& kv : blocks) {
    valid   += kv.second.getValidPageCount();
    invalid += kv.second.getDirtyPageCount();
  }
}

float PageMappingHotness::calculateWearLeveling() {
  // Jain's fairness index: (Σe)^2 / (N * Σe^2), N = 물리 블록 수
  const uint64_t numOfBlocks = param.totalPhysicalBlocks;

  uint64_t    totalErase = 0;     // Σe
  long double sumSq      = 0.0L;  // Σe^2

  // 활성 블록들
  for (auto& kv : blocks) {
    uint64_t e = kv.second.getEraseCount();   // Block::getEraseCount()가 non-const
    totalErase += e;
    sumSq      += (long double)e * e;
  }

  // 모든 풀(0..3)의 free 블록들
  for (int pool = 0; pool < 4; ++pool) {
    for (auto& b : freeBlocksByT[pool]) {
      uint64_t e = b.getEraseCount();         // 여기서도 non-const 필요
      totalErase += e;
      sumSq      += (long double)e * e;
    }
  }

  if (sumSq == 0.0L || numOfBlocks == 0) return -1.0f;
  long double numer = (long double)totalErase * totalErase;
  long double denom = (long double)numOfBlocks * sumSq;
  return (float)(numer / denom);
}

void PageMappingHotness::calculateVictimWeight(
    uint8_t t,
    std::vector<std::pair<uint32_t,float>>& weight,
    const EVICT_POLICY policy,
    uint64_t tick)
{
  weight.clear();
  weight.reserve(blocks.size());

  for (auto &kv : blocks) {
    // 같은 온도 풀의 '가득 찬' 블록만 후보
    auto itp = blockPool.find(kv.first);
    if (itp == blockPool.end() || itp->second != t) continue;

    if (kv.second.getNextWritePageIndex() != param.pagesInBlock) continue;

    switch (policy) {
      case POLICY_GREEDY:
      case POLICY_RANDOM:
      case POLICY_DCHOICE: {
        // 유효 페이지 수가 적을수록 가벼움
        float w = static_cast<float>(kv.second.getValidPageCountRaw());
        weight.emplace_back(kv.first, w);
        break;
      }
      case POLICY_COST_BENEFIT: {
        float u    = static_cast<float>(kv.second.getValidPageCountRaw()) /
                     static_cast<float>(param.pagesInBlock);  // 유효비율
        float age  = static_cast<float>(tick - kv.second.getLastAccessedTime());
        float denom = (1.0f - u) * (age <= 0.0f ? 1.0f : age);
        float w    = (denom <= 0.0f) ? std::numeric_limits<float>::infinity()
                                     : (u / denom);
        weight.emplace_back(kv.first, w);
        break;
      }
      default:
        panic("Invalid GC evict policy");
    }
  }
}


void PageMappingHotness::selectVictimBlock(uint8_t t,
                                           std::vector<uint32_t>& list,
                                           uint64_t& tick) {
  list.clear();

  // 1) 한 번에 회수할 블록 수 (설정이 0이면 최소 1 보장)
  uint64_t nBlocks = conf.readUint(CONFIG_FTL, FTL_GC_RECLAIM_BLOCK);
  if (nBlocks == 0) nBlocks = 1;

  // 2) 후보 weight 계산: "풀 t" 이면서 "이미 꽉 찬 블록"만
  std::vector<std::pair<uint32_t, float>> weight;
  weight.reserve(64);

  for (auto& kv : blocks) {
    uint32_t bid = kv.first;
    Block&   blk = kv.second;
    auto itp = blockPool.find(bid);
    if (itp == blockPool.end() || itp->second != t) continue;  // 다른 풀
    if (blk.getNextWritePageIndex() != param.pagesInBlock) continue; // 꽉 안 찬 블록 제외

    // GREEDY: 유효 페이지 수가 적을수록 유리
    weight.push_back({ bid, (float)blk.getValidPageCountRaw() });
  }

  if (weight.empty()) {
    tick += applyLatency(CPU::FTL__PAGE_MAPPING, CPU::SELECT_VICTIM_BLOCK);
    return;
  }

  std::sort(weight.begin(), weight.end(),
          [](const std::pair<uint32_t,float>& a,
             const std::pair<uint32_t,float>& b) {
            return a.second < b.second;
          });

  nBlocks = std::min<uint64_t>(nBlocks, weight.size());
  list.reserve(nBlocks);
  for (uint64_t i=0; i<nBlocks; ++i) list.push_back(weight[i].first);

  tick += applyLatency(CPU::FTL__PAGE_MAPPING, CPU::SELECT_VICTIM_BLOCK);
}


void PageMappingHotness::doGarbageCollection(uint8_t t,
                                             std::vector<uint32_t>& victims,
                                             uint64_t& tick) {
  if (victims.empty()) return;


  PAL::Request req(param.ioUnitInPage);
  std::vector<PAL::Request> reads, writes, erases;
  Bitset bit(param.ioUnitInPage);
  std::vector<uint64_t> lpns;
  uint64_t rFin=tick, wFin=tick, eFin=tick, beginAt=0;
  const uint32_t INVALID_BLK = std::numeric_limits<uint32_t>::max();

  uint32_t openDst[4] = {
  INVALID_BLK, INVALID_BLK, INVALID_BLK, INVALID_BLK
};

auto ensureOpenDst = [&](uint8_t pool, Bitset& iomap)->uint32_t {
  uint32_t& cur = openDst[pool];
  if (cur != INVALID_BLK) {
    auto it = blocks.find(cur);
    if (it != blocks.end() &&
        it->second.getNextWritePageIndex() < param.pagesInBlock) {
      // 아직 공간 남아 있으면 그대로 재사용
      return cur;
    }
    // 가득 찼거나 사라졌으면 무효화
    cur = INVALID_BLK;
  }
  // 새 오픈 블록 하나만 확보 (여기서 한 번만 getLastFreeBlock 호출)
  cur = getLastFreeBlock(pool, iomap);
  blockPool[cur] = pool; // 안전 태깅
  return cur;
};

  auto poolOf = [&](uint32_t blk)->uint8_t {
  auto itp = blockPool.find(blk);
    if (itp != blockPool.end() && 0 <= itp->second && itp->second < 4)
          return static_cast<uint8_t>(itp->second);
    stat.poolBug++;
    return t; // 못 찾으면 호출 인자 t로 폴백
    };
    uint64_t victimsPerPool[4] = {0,0,0,0};   

  for (auto bid : victims) {
    uint8_t pool = poolOf(bid);
    victimsPerPool[pool]++;

    auto it = blocks.find(bid);
    if (it == blocks.end()) panic("Invalid block");
    Block& vblk = it->second;

    for (uint32_t pg=0; pg<param.pagesInBlock; ++pg) {
      if (!vblk.getPageInfo(pg, lpns, bit)) continue;
      Bitset bitValid = bit;
      if (!bRandomTweak) bit.set();

      // victim에서 읽기 예약
req.blockIndex = bid; req.pageIndex = pg; req.ioFlag = bit;
reads.push_back(req);

// ★ 데스티네이션: 같은 풀(pool)의 '열려 있는' 오픈 블록을 우선 사용
uint32_t newBlkId = ensureOpenDst(pool, bit);
auto freeIt = blocks.find(newBlkId);
if (freeIt == blocks.end()) panic("No free block allocated");
Block* dst = &freeIt->second;   // 포인터로 잡아두면 중간에 새 블록으로 스위칭 용이
bool copied = false;            // 이 superpage(페이지)에 실제 복사 발생 여부

// 유효 서브페이지별 복사 + 매핑 갱신
for (uint32_t k = 0; k < bitsetSize; ++k) if (bit.test(k)) {
  if (k >= lpns.size()) continue;
  // ★ 중간에 데스티네이션 블록이 꽉 차면 즉시 새 오픈 블록으로 전환
  if (dst->getNextWritePageIndex() >= param.pagesInBlock) {
    openDst[pool] = INVALID_BLK;          // 캐시 무효화
    newBlkId = ensureOpenDst(pool, bit);                 // 새 오픈 블록 확보
    auto it2 = blocks.find(newBlkId);
    if (it2 == blocks.end()) panic("No free block allocated");
    dst = &it2->second;                                  // 포인터 리바인딩
  }

  vblk.invalidate(pg, k);
  auto mIt = table.find(lpns[k]); if (mIt == table.end()) panic("Invalid mapping");
  if (bRandomTweak) pDRAM->read(&(*mIt), 8 * param.ioUnitInPage, tick);
  else               pDRAM->read(&(*mIt), 8, tick);

  uint32_t newPg = dst->getNextWritePageIndex(k);
  beginAt = tick;                          // writeInternal과 동일하게 tick 기준
  dst->write(newPg, lpns[k], k, beginAt);

  auto& mapping = mIt->second.at(k);
  mapping.first  = newBlkId;
  mapping.second = newPg;

  if (bRandomTweak) pDRAM->write(&(*mIt), 8 * param.ioUnitInPage, tick);
  else               pDRAM->write(&(*mIt), 8, tick);

  req.blockIndex = newBlkId; req.pageIndex = newPg;
  if (bRandomTweak) { req.ioFlag.reset(); req.ioFlag.set(k); } else { req.ioFlag.set(); }
  writes.push_back(req);

  //stat.validPageCopies[pool]++;
  copied = true;
}

// (선택) 페이지 종료 시점에 한 번 더 꽉 참 체크 → 다음 ensure에서 새로 열리도록
if (dst->getNextWritePageIndex() >= param.pagesInBlock) {
  openDst[pool] = INVALID_BLK;
}
// ★ 페이지(pg) 단위 처리 끝난 뒤, 실제 복사된 서브페이지 수를 누적
const uint32_t nvalid = bitValid.count();   // <- 추가
if (copied && nvalid > 0) {
  stat.validSuperPageCopies[pool]++;        // 기존 유지
  stat.validPageCopies[pool] += nvalid;     // <- 기존의 ++ 대신 이 줄로 이동/교체
}

}
    // ERASE 예약
    req.blockIndex = bid; req.pageIndex = 0; req.ioFlag.set();
    erases.push_back(req);
  }
  for (int p=0; p<4; ++p) {
      if (victimsPerPool[p] > 0) {
        stat.gcCount[p]         += victimsPerPool[p];
        stat.reclaimedBlocks[p] += victimsPerPool[p];
      }
    }

  for (auto& r: reads)  { beginAt=tick; pPAL->read(r, beginAt);  rFin = std::max(rFin, beginAt); }
  for (auto& w: writes) { beginAt=rFin; pPAL->write(w, beginAt); 
    {
        const uint64_t bytesPerSub = param.pageSize / param.ioUnitInPage;
  const uint64_t devBytesRaw = bytesPerSub * static_cast<uint64_t>(w.ioFlag.count());
  const uint64_t devBytes    = devBytesRaw / 2;
  stat.nandProgramBytes += devBytes;
}

  wFin = std::max(wFin, beginAt); }
  for (auto& e: erases) { beginAt = wFin; eraseInternal(e, beginAt); eFin = std::max(eFin, beginAt); }

  tick = std::max(wFin, eFin);
  tick += applyLatency(CPU::FTL__PAGE_MAPPING, CPU::DO_GARBAGE_COLLECTION);
}



void PageMappingHotness::getStatList(std::vector<Stats>& list, std::string prefix) {
  // 기본 PageMapping 이름과 충돌 안나게 hotness 접두사 사용
  for (int t=0; t<4; ++t) {
    Stats s;
    s.name = prefix + "page_mapping_hotness.gc.count.t" + std::to_string(t);
    s.desc = "GC count for pool t" + std::to_string(t);
    list.push_back(s);

    s.name = prefix + "page_mapping_hotness.gc.reclaimed_blocks.t" + std::to_string(t);
    s.desc = "Reclaimed blocks in GC for pool t" + std::to_string(t);
    list.push_back(s);

    s.name = prefix + "page_mapping_hotness.gc.superpage_copies.t" + std::to_string(t);
    s.desc = "Copied valid superpages in GC (pool t)";
    list.push_back(s);

    s.name = prefix + "page_mapping_hotness.gc.page_copies.t" + std::to_string(t);
    s.desc = "Copied valid pages in GC (pool t)";
    list.push_back(s);
  }
  // 초기 free
/*for (int t=0; t<4; ++t) {
  Stats s;
  s.name = prefix + "page_mapping_hotness.init_free.t" + std::to_string(t);
  s.desc = "Initial free blocks in pool t" + std::to_string(t);
  list.push_back(s);
}*/


// 요청/사용 분포
for (int t=0; t<4; ++t) {
  Stats s1, s2;
  s1.name = prefix + "page_mapping_hotness.writes_req.t" + std::to_string(t);
  s1.desc = "Writes by requested label t" + std::to_string(t);
  list.push_back(s1);
  s2.name = prefix + "page_mapping_hotness.writes_use.t" + std::to_string(t);
  s2.desc = "Writes by actual pool t" + std::to_string(t);
  list.push_back(s2);
}

// 폴백 4x4
//for (int r=0; r<4; ++r) for (int u=0; u<4; ++u) {
  //Stats s;
//  s.name = prefix + "page_mapping_hotness.fallback.req" + std::to_string(r)
//         + "_to" + std::to_string(u);
//  s.desc = "Fallback from req tier " + std::to_string(r)
//         + " to use tier " + std::to_string(u);
//  list.push_back(s);
//}


// free pop 카운트
//for (int t=0; t<4; ++t) {
//  Stats s;
//  s.name = prefix + "page_mapping_hotness.alloc.pop.t" + std::to_string(t);
//  s.desc = "Pops from free list (pool t)";
//  list.push_back(s);
//}


// pool 태깅 누락
{
  Stats s;
  s.name = prefix + "page_mapping_hotness.pool_bug";
  s.desc = "Victims with missing/invalid pool tag";
  list.push_back(s);
}

  Stats wl;
  wl.name = prefix + "page_mapping_hotness.wear_leveling";
  wl.desc = "Wear-leveling factor (approx.)";
  list.push_back(wl);

  {// (교체) W/A 관련 통계 키
{
  Stats s;

  s.name = prefix + "page_mapping_hotness.wa.ftl_new_prog_bytes";
  s.desc = "FTL new-program bytes (excl. GC)"; // GC 복사 제외한 실제 신규 프로그램 바이트
  list.push_back(s);

  s.name = prefix + "page_mapping_hotness.wa.device_total_bytes";
  s.desc = "Total NAND program bytes (incl. GC)"; // 기존 desc 유지 가능
  list.push_back(s);

  s.name = prefix + "page_mapping_hotness.wa.gc_only";
  s.desc = "Write Amplification (GC-only) = device_total_bytes / ftl_new_prog_bytes";
  list.push_back(s);
}

}
}

void PageMappingHotness::getStatValues(std::vector<double>& values) {
  const int TIERS = 4;
  const size_t base = values.size();
  values.reserve( base + 
      TIERS*4      /*gc*/
  //  + TIERS        /*init_free*/
    + TIERS*2      /*writes req/use*/
  //  + TIERS*TIERS  /*fallback*/
   // + TIERS        /*alloc.pop*/
    + 1            /*pool_bug*/
    + 1            /*wear*/
    +3 
  );

  // ---- GC (등록 순서와 동일) ----
  for (int t = 0; t < TIERS; ++t) {
    values.push_back((double)stat.gcCount[t]);
    values.push_back((double)stat.reclaimedBlocks[t]);
    values.push_back((double)stat.validSuperPageCopies[t]);
    values.push_back((double)stat.validPageCopies[t]);
  }

  // ---- init_free ----
  //for (int t=0; t<4; ++t) values.push_back((double)stat.initFree[t]);

  // ---- writes_req / writes_use ----
  for (int t=0; t<4; ++t) {
  values.push_back((double)stat.writesReq[t]);
  values.push_back((double)stat.writesUse[t]);
}

  // ---- fallback 4x4 ----
  //for (int r=0; r<4; ++r) for (int u=0; u<4; ++u)
  //  values.push_back((double)stat.fallback[r][u]);

  // ---- alloc.pop ----
  //for (int t=0; t<4; ++t) values.push_back((double)stat.allocPop[t]);

  // ---- pool_bug ----
  values.push_back((double)stat.poolBug);

  // ---- wear_leveling (마지막) ----
  values.push_back((double)calculateWearLeveling());

  // --- W/A (GC-only) 산출: devBytes / ftlNewBytes ---
const uint64_t bytesPerSub =
    param.pageSize / param.ioUnitInPage; // 서브페이지(4KiB) → 물리 페이지 바이트 분배

const uint64_t devBytes = stat.nandProgramBytes; // 총 NAND program 바이트(=신규+GC)

// GC가 복사한 서브페이지 수 합
const uint64_t gcSubCopies =
    (uint64_t)stat.validPageCopies[0] +
    (uint64_t)stat.validPageCopies[1] +
    (uint64_t)stat.validPageCopies[2] +
    (uint64_t)stat.validPageCopies[3];

// devBytes 누적과 동일한 규칙(/2)으로 GC 바이트 환산
const uint64_t gcBytes = (gcSubCopies * bytesPerSub) / 2;

// FTL 신규 프로그램 바이트(= devBytes - gcBytes)
const uint64_t ftlNewBytes = (devBytes > gcBytes) ? (devBytes - gcBytes) : 0;

const double wafGcOnly = ftlNewBytes
  ? (double)devBytes / (double)ftlNewBytes
  : 0.0;

// --- 출력(등록 순서: ftl_new_prog_bytes, device_total_bytes, gc_only) ---
values.push_back((double)ftlNewBytes);
values.push_back((double)devBytes);
values.push_back(wafGcOnly);


}
}
}