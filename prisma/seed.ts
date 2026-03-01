import "dotenv/config";
import { PrismaClient } from "@prisma/client";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";
import { readFileSync } from "fs";
import { join } from "path";

const adapter = new PrismaBetterSqlite3({
  url: process.env.DATABASE_URL || "file:./prisma/dev.db",
});
const prisma = new PrismaClient({ adapter });

interface MinistryData {
  slug: string;
  name: string;
  nameEn: string;
  url: string;
  councilUrl: string | null;
  color: string;
  sortOrder: number;
}

async function main() {
  console.log("Seeding ministries...");

  const raw = readFileSync(join(__dirname, "..", "data", "ministries.json"), "utf-8");
  const ministries: MinistryData[] = JSON.parse(raw);

  for (const m of ministries) {
    await prisma.ministry.upsert({
      where: { slug: m.slug },
      update: {
        name: m.name,
        nameEn: m.nameEn,
        url: m.url,
        councilUrl: m.councilUrl,
        color: m.color,
        sortOrder: m.sortOrder,
      },
      create: {
        slug: m.slug,
        name: m.name,
        nameEn: m.nameEn,
        url: m.url,
        councilUrl: m.councilUrl,
        color: m.color,
        sortOrder: m.sortOrder,
      },
    });
  }

  const count = await prisma.ministry.count();
  console.log(`Seeded ${count} ministries.`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
