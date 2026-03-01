import "dotenv/config";
import { PrismaClient } from "@prisma/client";
import { PrismaLibSql } from "@prisma/adapter-libsql";
import { readFileSync } from "fs";
import { join } from "path";

const adapter = new PrismaLibSql({
  url: process.env.TURSO_DATABASE_URL!,
  authToken: process.env.TURSO_AUTH_TOKEN,
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
