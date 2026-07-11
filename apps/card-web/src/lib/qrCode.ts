const VERSION = 10;
const SIZE = VERSION * 4 + 17;
const DATA_CODEWORDS = 274;
const ERROR_CODEWORDS_PER_BLOCK = 18;
const DATA_BLOCK_LENGTHS = [68, 68, 69, 69] as const;
const ALIGNMENT_PATTERN_POSITIONS = [6, 28, 50] as const;

type MutableMatrix = Array<Array<boolean | null>>;

function appendBits(target: number[], value: number, length: number) {
  for (let bit = length - 1; bit >= 0; bit -= 1) {
    target.push(((value >>> bit) & 1) !== 0 ? 1 : 0);
  }
}

function buildDataCodewords(value: string) {
  const bytes = [...new TextEncoder().encode(value)];
  const bits: number[] = [];
  appendBits(bits, 0b0100, 4);
  appendBits(bits, bytes.length, 16);
  for (const byte of bytes) appendBits(bits, byte, 8);

  const capacityBits = DATA_CODEWORDS * 8;
  if (bits.length > capacityBits) {
    throw new Error("分享链接过长，无法生成本地二维码");
  }
  appendBits(bits, 0, Math.min(4, capacityBits - bits.length));
  while (bits.length % 8 !== 0) bits.push(0);

  const result: number[] = [];
  for (let index = 0; index < bits.length; index += 8) {
    let byte = 0;
    for (let offset = 0; offset < 8; offset += 1) {
      byte = (byte << 1) | bits[index + offset];
    }
    result.push(byte);
  }
  for (let pad = 0; result.length < DATA_CODEWORDS; pad += 1) {
    result.push(pad % 2 === 0 ? 0xec : 0x11);
  }
  return result;
}

function multiplyInGaloisField(left: number, right: number) {
  let x = left;
  let y = right;
  let result = 0;
  for (let bit = 0; bit < 8; bit += 1) {
    result ^= (y & 1) !== 0 ? x : 0;
    const carry = (x & 0x80) !== 0;
    x = (x << 1) & 0xff;
    if (carry) x ^= 0x1d;
    y >>>= 1;
  }
  return result;
}

function reedSolomonDivisor(degree: number) {
  const result = Array<number>(degree).fill(0);
  result[degree - 1] = 1;
  let root = 1;
  for (let index = 0; index < degree; index += 1) {
    for (let coefficient = 0; coefficient < result.length; coefficient += 1) {
      result[coefficient] = multiplyInGaloisField(result[coefficient], root);
      if (coefficient + 1 < result.length) {
        result[coefficient] ^= result[coefficient + 1];
      }
    }
    root = multiplyInGaloisField(root, 0x02);
  }
  return result;
}

function reedSolomonRemainder(data: number[], divisor: number[]) {
  const result = Array<number>(divisor.length).fill(0);
  for (const byte of data) {
    const factor = byte ^ result.shift()!;
    result.push(0);
    divisor.forEach((coefficient, index) => {
      result[index] ^= multiplyInGaloisField(coefficient, factor);
    });
  }
  return result;
}

function addErrorCorrection(data: number[]) {
  const divisor = reedSolomonDivisor(ERROR_CODEWORDS_PER_BLOCK);
  const blocks: number[][] = [];
  const errorBlocks: number[][] = [];
  let offset = 0;
  for (const length of DATA_BLOCK_LENGTHS) {
    const block = data.slice(offset, offset + length);
    offset += length;
    blocks.push(block);
    errorBlocks.push(reedSolomonRemainder(block, divisor));
  }

  const result: number[] = [];
  const longestBlock = Math.max(...DATA_BLOCK_LENGTHS);
  for (let index = 0; index < longestBlock; index += 1) {
    for (const block of blocks) {
      if (index < block.length) result.push(block[index]);
    }
  }
  for (let index = 0; index < ERROR_CODEWORDS_PER_BLOCK; index += 1) {
    for (const block of errorBlocks) result.push(block[index]);
  }
  return result;
}

function emptyMatrix(): MutableMatrix {
  return Array.from({ length: SIZE }, () => Array<boolean | null>(SIZE).fill(null));
}

function emptyFunctionMap() {
  return Array.from({ length: SIZE }, () => Array<boolean>(SIZE).fill(false));
}

function drawFunctionPatterns() {
  const matrix = emptyMatrix();
  const functionModules = emptyFunctionMap();
  const set = (x: number, y: number, dark: boolean) => {
    if (x < 0 || x >= SIZE || y < 0 || y >= SIZE) return;
    matrix[y][x] = dark;
    functionModules[y][x] = true;
  };

  for (let index = 0; index < SIZE; index += 1) {
    set(6, index, index % 2 === 0);
    set(index, 6, index % 2 === 0);
  }

  const drawFinder = (centerX: number, centerY: number) => {
    for (let y = -4; y <= 4; y += 1) {
      for (let x = -4; x <= 4; x += 1) {
        const distance = Math.max(Math.abs(x), Math.abs(y));
        set(centerX + x, centerY + y, distance !== 2 && distance !== 4);
      }
    }
  };
  drawFinder(3, 3);
  drawFinder(SIZE - 4, 3);
  drawFinder(3, SIZE - 4);

  const drawAlignment = (centerX: number, centerY: number) => {
    for (let y = -2; y <= 2; y += 1) {
      for (let x = -2; x <= 2; x += 1) {
        set(
          centerX + x,
          centerY + y,
          Math.max(Math.abs(x), Math.abs(y)) !== 1,
        );
      }
    }
  };
  const last = ALIGNMENT_PATTERN_POSITIONS.length - 1;
  ALIGNMENT_PATTERN_POSITIONS.forEach((x, xIndex) => {
    ALIGNMENT_PATTERN_POSITIONS.forEach((y, yIndex) => {
      const overlapsFinder =
        (xIndex === 0 && yIndex === 0) ||
        (xIndex === 0 && yIndex === last) ||
        (xIndex === last && yIndex === 0);
      if (!overlapsFinder) drawAlignment(x, y);
    });
  });

  drawVersionBits(set);
  drawFormatBits(set, 0);
  return { matrix, functionModules };
}

function bit(value: number, index: number) {
  return ((value >>> index) & 1) !== 0;
}

function drawVersionBits(set: (x: number, y: number, dark: boolean) => void) {
  let remainder = VERSION;
  for (let index = 0; index < 12; index += 1) {
    remainder = (remainder << 1) ^ ((remainder >>> 11) * 0x1f25);
  }
  const bits = (VERSION << 12) | remainder;
  for (let index = 0; index < 18; index += 1) {
    const dark = bit(bits, index);
    const first = SIZE - 11 + (index % 3);
    const second = Math.floor(index / 3);
    set(first, second, dark);
    set(second, first, dark);
  }
}

function drawFormatBits(
  set: (x: number, y: number, dark: boolean) => void,
  mask: number,
) {
  const data = (0b01 << 3) | mask;
  let remainder = data;
  for (let index = 0; index < 10; index += 1) {
    remainder = (remainder << 1) ^ ((remainder >>> 9) * 0x537);
  }
  const bits = ((data << 10) | remainder) ^ 0x5412;

  for (let index = 0; index <= 5; index += 1) set(8, index, bit(bits, index));
  set(8, 7, bit(bits, 6));
  set(8, 8, bit(bits, 7));
  set(7, 8, bit(bits, 8));
  for (let index = 9; index < 15; index += 1) {
    set(14 - index, 8, bit(bits, index));
  }
  for (let index = 0; index < 8; index += 1) {
    set(SIZE - 1 - index, 8, bit(bits, index));
  }
  for (let index = 8; index < 15; index += 1) {
    set(8, SIZE - 15 + index, bit(bits, index));
  }
  set(8, SIZE - 8, true);
}

function maskApplies(mask: number, x: number, y: number) {
  switch (mask) {
    case 0:
      return (x + y) % 2 === 0;
    case 1:
      return y % 2 === 0;
    case 2:
      return x % 3 === 0;
    case 3:
      return (x + y) % 3 === 0;
    case 4:
      return (Math.floor(y / 2) + Math.floor(x / 3)) % 2 === 0;
    case 5:
      return ((x * y) % 2) + ((x * y) % 3) === 0;
    case 6:
      return (((x * y) % 2) + ((x * y) % 3)) % 2 === 0;
    case 7:
      return (((x + y) % 2) + ((x * y) % 3)) % 2 === 0;
    default:
      return false;
  }
}

function drawCodewords(
  base: MutableMatrix,
  functionModules: boolean[][],
  codewords: number[],
  mask: number,
) {
  const matrix = base.map((row) => [...row]);
  let dataIndex = 0;
  for (let right = SIZE - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let vertical = 0; vertical < SIZE; vertical += 1) {
      const upward = ((right + 1) & 2) === 0;
      const y = upward ? SIZE - 1 - vertical : vertical;
      for (let offset = 0; offset < 2; offset += 1) {
        const x = right - offset;
        if (functionModules[y][x]) continue;
        const codeword = codewords[dataIndex >>> 3] ?? 0;
        let dark = bit(codeword, 7 - (dataIndex & 7));
        if (maskApplies(mask, x, y)) dark = !dark;
        matrix[y][x] = dark;
        dataIndex += 1;
      }
    }
  }

  drawFormatBits((x, y, dark) => {
    matrix[y][x] = dark;
  }, mask);
  return matrix.map((row) => row.map((module) => module === true));
}

function runPenalty(values: boolean[]) {
  let result = 0;
  let runLength = 1;
  for (let index = 1; index <= values.length; index += 1) {
    if (index < values.length && values[index] === values[index - 1]) {
      runLength += 1;
      continue;
    }
    if (runLength >= 5) result += 3 + (runLength - 5);
    runLength = 1;
  }
  return result;
}

function finderPenalty(values: boolean[]) {
  const patternA = "00001011101";
  const patternB = "10111010000";
  const serialized = values.map((value) => (value ? "1" : "0")).join("");
  let result = 0;
  for (let index = 0; index <= serialized.length - 11; index += 1) {
    const candidate = serialized.slice(index, index + 11);
    if (candidate === patternA || candidate === patternB) result += 40;
  }
  return result;
}

function penaltyScore(matrix: boolean[][]) {
  let result = 0;
  let darkModules = 0;
  for (let index = 0; index < SIZE; index += 1) {
    const row = matrix[index];
    const column = matrix.map((candidate) => candidate[index]);
    result += runPenalty(row) + runPenalty(column);
    result += finderPenalty(row) + finderPenalty(column);
    darkModules += row.filter(Boolean).length;
  }
  for (let y = 0; y < SIZE - 1; y += 1) {
    for (let x = 0; x < SIZE - 1; x += 1) {
      const color = matrix[y][x];
      if (
        matrix[y][x + 1] === color &&
        matrix[y + 1][x] === color &&
        matrix[y + 1][x + 1] === color
      ) {
        result += 3;
      }
    }
  }
  const total = SIZE * SIZE;
  result += Math.floor(Math.abs(darkModules * 20 - total * 10) / total) * 10;
  return result;
}

export function encodeQrMatrix(value: string) {
  if (!value.trim()) throw new Error("二维码内容不能为空");
  const codewords = addErrorCorrection(buildDataCodewords(value));
  const { matrix: base, functionModules } = drawFunctionPatterns();
  let bestMatrix: boolean[][] | undefined;
  let bestPenalty = Number.POSITIVE_INFINITY;
  for (let mask = 0; mask < 8; mask += 1) {
    const candidate = drawCodewords(base, functionModules, codewords, mask);
    const penalty = penaltyScore(candidate);
    if (penalty < bestPenalty) {
      bestPenalty = penalty;
      bestMatrix = candidate;
    }
  }
  return bestMatrix!;
}

export function qrPathData(matrix: boolean[][], border = 4) {
  const commands: string[] = [];
  matrix.forEach((row, y) => {
    row.forEach((dark, x) => {
      if (dark) commands.push(`M${x + border},${y + border}h1v1h-1z`);
    });
  });
  return commands.join("");
}
