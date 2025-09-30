#ifndef __FTL_PAGE_MAPPING_HOTNESS__
#define __FTL_PAGE_MAPPING_HOTNESS__

#include <array>
#include <list>
#include <unordered_map>
#include <vector>

#include "ftl/abstract_ftl.hh"
#include "ftl/common/block.hh"
#include "ftl/ftl.hh"
#include "pal/pal.hh"

namespace SimpleSSD { namespace FTL {

class PageMappingHotness : public AbstractFTL {
 private:
  PAL::PAL* pPAL;
  ConfigReader& conf;
  // LPN -> [(block,page) * ioUnitInPage]
  std::unordered_map<uint64_t, std::vector<std::pair<uint32_t,uint32_t>>> table;

  // 활성 블록(실사용)
  std::unordered_map<uint32_t, Block> blocks;

  // 온도별 free block 풀 (0..3)
  std::array<std::list<Block>,4> freeBlocksByT {};
  std::array<uint32_t,4>        nFreeByT      {{0,0,0,0}};

  // 블록이 어느 풀(온도)에 속하는지
  std::unordered_map<uint32_t, uint8_t> blockPool;

  // 온도별 최근 free block (채널/스트라이프 수만큼)
  std::array<std::vector<uint32_t>,4> lastFreeBlockByT;
  std::array<uint32_t,4>              lastFreeIdx   {{0,0,0,0}};
  Bitset                               lastFreeBlockIOMap;

  // LPN의 최신 temperature 라벨
  std::unordered_map<uint64_t, uint8_t> lpnTemp;


  bool bReclaimMore = false;
  bool bRandomTweak;
  uint32_t bitsetSize;
  uint32_t reservePerPool;                 // 각 풀당 예비 블록 개수

  inline uint8_t clampTemp(int t) const { return (t < 0) ? 0 : (t > 3 ? 3 : (uint8_t)t); }

  // helpers
  float    freeBlockRatio(uint8_t t);
  uint32_t getFreeBlock(uint8_t t, uint32_t stripeIdx);
  uint32_t getLastFreeBlock(uint8_t t, Bitset& iomap);
  uint32_t borrowFreeBlock(uint8_t t, uint32_t stripeIdx);
  
  void calculateVictimWeight(uint8_t t,
      std::vector<std::pair<uint32_t,float>>& weight,
      const EVICT_POLICY policy, uint64_t tick);

  void selectVictimBlock(uint8_t t, std::vector<uint32_t>& list, uint64_t& tick);
  void doGarbageCollection(uint8_t t, std::vector<uint32_t>& blocksToReclaim, uint64_t& tick);

  void readInternal(Request& req, uint64_t& tick);
  void writeInternal(Request& req, uint64_t& tick, bool sendToPAL = true);
  void trimInternal(Request& req, uint64_t& tick);
  void eraseInternal(PAL::Request& req, uint64_t& tick);

  float calculateWearLeveling();
  void  calculateTotalPages(uint64_t& valid, uint64_t& invalid);

  struct {
    uint64_t gcCount[4] {};
    uint64_t reclaimedBlocks[4] {};
    uint64_t validSuperPageCopies[4] {};
    uint64_t validPageCopies[4] {};

    uint64_t initFree[4]             = {0,0,0,0}; // 시작 시 풀별 free 스냅샷
    uint64_t writesReq[4]            = {0,0,0,0}; // 요청 라벨 분포
    uint64_t writesUse[4]            = {0,0,0,0}; // 실제 사용 풀 분포
    uint64_t fallback[4][4]          = {{0}};     // [req][use] 폴백 매트릭스
    uint64_t allocPop[4]             = {0,0,0,0}; // free 리스트에서 꺼낸 횟수(풀 기준)
    int64_t poolBug                 = 0;         // GC에서 blockPool 태깅 못 찾은 횟수

    uint64_t hostProgramBytes = 0;  // 호스트로 인해 FTL이 실제 프로그램한 바이트
    uint64_t nandProgramBytes = 0; // 디바이스 Program 총 바이트(분자, GC 포함)
    uint64_t gcProgramBytes = 0; // GC로 인해 실제 디바이스에 프로그램된 바이트 누적
  } stat;

 public:
  PageMappingHotness(ConfigReader& c, Parameter& p, PAL::PAL* l, DRAM::AbstractDRAM* d);
  ~PageMappingHotness();

  bool initialize() override;

  void read(Request& req, uint64_t& tick) override;
  void write(Request& req, uint64_t& tick) override;
  void trim(Request& req, uint64_t& tick) override;

  void format(LPNRange& range, uint64_t& tick) override;

  Status* getStatus(uint64_t lpnBegin, uint64_t lpnEnd) override;

  void getStatList(std::vector<Stats>& list, std::string prefix) override;
  void getStatValues(std::vector<double>& values) override;
  void resetStatValues() override;
};

}} // namespace

#endif
