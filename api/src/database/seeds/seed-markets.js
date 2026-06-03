const DimMarket = require('../models/dim-market.model');

const seedMarkets = async () => {
  const markets = [
    {
      code: 'HOSE',
      name: 'Ho Chi Minh Stock Exchange',
      country: 'Vietnam',
      timezone: 'Asia/Ho_Chi_Minh',
      status: 'active'
    },
    {
      code: 'HNX',
      name: 'Hanoi Stock Exchange',
      country: 'Vietnam',
      timezone: 'Asia/Ho_Chi_Minh',
      status: 'active'
    },
    {
      code: 'UPCOM',
      name: 'Unlisted Public Company Market',
      country: 'Vietnam',
      timezone: 'Asia/Ho_Chi_Minh',
      status: 'active'
    }
  ];

  const seeded = [];
  for (const m of markets) {
    let exist = await DimMarket.findOne({ code: m.code });
    if (!exist) {
      exist = await DimMarket.create(m);
      console.log(`[Seed] Created market: ${m.code}`);
    } else {
      // Cập nhật các field mới nếu record cũ đang thiếu
      await DimMarket.findOneAndUpdate({ code: m.code }, {
        $set: {
          country: m.country,
          timezone: m.timezone,
          status: m.status
        }
      });
      exist = await DimMarket.findOne({ code: m.code });
      console.log(`[Seed] Market ${m.code} already exists — updated.`);
    }
    seeded.push(exist);
  }
  return seeded;
};

module.exports = seedMarkets;
