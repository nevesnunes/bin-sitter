vim.o.display = 'uhex'
vim.o.fileencoding = 'latin1'
vim.o.fileencodings = 'latin1'
vim.o.fileformats = 'unix'
vim.o.fileformat = 'unix'
vim.o.fixendofline = false

vim.filetype.add({
  pattern = {
    ['.*.bin'] = 'bin',
    ['.*.elf'] = 'elf',
  },
})

local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.loop.fs_stat(lazypath) then
  vim.fn.system({
    "git",
    "clone",
    "--filter=blob:none",
    "https://github.com/folke/lazy.nvim.git",
    "--branch=stable",
    lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

require("lazy").setup({
  {
    "nvim-treesitter/nvim-treesitter",
    branch = 'master',
    build = ":TSUpdate",
    config = function()
      require("nvim-treesitter.configs").setup({
        highlight = {enable = true},
      })
    end,
    event = { "BufReadPost", "BufNewFile" },
    lazy = false
  }
})

local parser_config = require("nvim-treesitter.parsers").get_parser_configs()
parser_config.ptrs = {
    install_info = {
        url = "~/code/my/bin-sitter/tree-sitter-ptrs",
        files = { "src/parser.c", "src/scanner.c" },
        generate_requires_npm = false,
        requires_generate_from_grammar = false,
    },
    filetype = "bin",
}
parser_config.elf = {
    install_info = {
        url = "~/code/my/bin-sitter/tree-sitter-elf",
        files = { "src/parser.c", "src/scanner.c" },
        generate_requires_npm = false,
        requires_generate_from_grammar = false,
    },
    filetype = "elf",
}

vim.api.nvim_create_autocmd({ 'BufReadPost', 'CursorMoved', }, {
  pattern = { "*.bin", "*.elf" },
  callback = function()
    vim.api.nvim_set_hl(0, 'SpecialKey', { })
  end,
})

local hi = function(name, val)
  -- Force links
  val.force = true

  -- Make sure that `cterm` attribute is not populated from `gui`
  val.cterm = val.cterm or {} ---@type vim.api.keyset.highlight

  -- Define global highlight
  vim.api.nvim_set_hl(0, name, val)
end

--stylua: ignore start
if vim.o.background == 'light' then
  -- Default colors only used with a light background.
  hi('BS0', { fg = 'DarkCyan', bold = true,    ctermfg = 'Cyan', cterm = { bold = true } })
  hi('BS1', { fg = 'DarkRed', bold = true,     ctermfg = 'Red', cterm = { bold = true } })
  hi('BS2', { fg = 'DarkGreen', bold = true,   ctermfg = 'Green', cterm = { bold = true } })
  hi('BS3', { fg = 'DarkMagenta', bold = true, ctermfg = 'Magenta', cterm = { bold = true } })
  hi('BS4', { fg = 'DarkBlue', bold = true,    ctermfg = 'Blue', cterm = { bold = true } })
else
  -- Default colors only used with a dark background.
  hi('BS0', { fg = 'LightCyan', bold = true,    ctermfg = 'Cyan', cterm = { bold = true } })
  hi('BS1', { fg = 'LightRed', bold = true,     ctermfg = 'Red', cterm = { bold = true } })
  hi('BS2', { fg = 'LightGreen', bold = true,   ctermfg = 'Green', cterm = { bold = true } })
  hi('BS3', { fg = 'LightMagenta', bold = true, ctermfg = 'Magenta', cterm = { bold = true } })
  hi('BS4', { fg = 'LightBlue', bold = true,    ctermfg = 'Blue', cterm = { bold = true } })
end
hi('@bs0', { link = 'BS0' })
hi('@bs1', { link = 'BS1' })
hi('@bs2', { link = 'BS2' })
hi('@bs3', { link = 'BS3' })
hi('@bs4', { link = 'BS4' })
--stylua: ignore end
